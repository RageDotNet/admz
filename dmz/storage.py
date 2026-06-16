"""SQLite-backed persistent queue storage."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).parent.parent / "data" / "dmz.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RequestRecord:
    request_id: str
    schema_id: str
    requestor_id: str
    requestee_id: str
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None
    status: str
    validation_errors: str | None
    arbiter_request_notes: str | None
    arbiter_response_notes: str | None
    created_at: str
    updated_at: str


@dataclass
class ReviewItem:
    id: str
    request_id: str
    review_type: str
    reason: str
    payload_snapshot: dict[str, Any]
    status: str
    reviewer_id: str | None
    reviewer_notes: str | None
    created_at: str
    updated_at: str


class Storage:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    request_id TEXT PRIMARY KEY,
                    schema_id TEXT NOT NULL,
                    requestor_id TEXT NOT NULL,
                    requestee_id TEXT NOT NULL,
                    request_payload TEXT NOT NULL,
                    response_payload TEXT,
                    status TEXT NOT NULL,
                    validation_errors TEXT,
                    arbiter_request_notes TEXT,
                    arbiter_response_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS review_queue (
                    id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    review_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload_snapshot TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reviewer_id TEXT,
                    reviewer_notes TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_requests_status_requestee
                    ON requests(status, requestee_id);
                CREATE INDEX IF NOT EXISTS idx_requests_status_requestor
                    ON requests(status, requestor_id);
                CREATE INDEX IF NOT EXISTS idx_review_status
                    ON review_queue(status);
                """
            )

    def _row_to_request(self, row: sqlite3.Row) -> RequestRecord:
        return RequestRecord(
            request_id=row["request_id"],
            schema_id=row["schema_id"],
            requestor_id=row["requestor_id"],
            requestee_id=row["requestee_id"],
            request_payload=json.loads(row["request_payload"]),
            response_payload=json.loads(row["response_payload"]) if row["response_payload"] else None,
            status=row["status"],
            validation_errors=row["validation_errors"],
            arbiter_request_notes=row["arbiter_request_notes"],
            arbiter_response_notes=row["arbiter_response_notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_review(self, row: sqlite3.Row) -> ReviewItem:
        return ReviewItem(
            id=row["id"],
            request_id=row["request_id"],
            review_type=row["review_type"],
            reason=row["reason"],
            payload_snapshot=json.loads(row["payload_snapshot"]),
            status=row["status"],
            reviewer_id=row["reviewer_id"],
            reviewer_notes=row["reviewer_notes"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_request(
        self,
        *,
        request_id: str,
        schema_id: str,
        requestor_id: str,
        requestee_id: str,
        request_payload: dict[str, Any],
    ) -> RequestRecord:
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO requests (
                    request_id, schema_id, requestor_id, requestee_id,
                    request_payload, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    schema_id,
                    requestor_id,
                    requestee_id,
                    json.dumps(request_payload),
                    "validating",
                    now,
                    now,
                ),
            )
        return self.get_request(request_id)

    def get_request(self, request_id: str) -> RequestRecord:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM requests WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown request_id: {request_id}")
        return self._row_to_request(row)

    def update_request(
        self,
        request_id: str,
        *,
        status: str | None = None,
        response_payload: dict[str, Any] | None = None,
        validation_errors: str | None = None,
        arbiter_request_notes: str | None = None,
        arbiter_response_notes: str | None = None,
    ) -> RequestRecord:
        fields: list[str] = []
        values: list[Any] = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if response_payload is not None:
            fields.append("response_payload = ?")
            values.append(json.dumps(response_payload))
        if validation_errors is not None:
            fields.append("validation_errors = ?")
            values.append(validation_errors)
        if arbiter_request_notes is not None:
            fields.append("arbiter_request_notes = ?")
            values.append(arbiter_request_notes)
        if arbiter_response_notes is not None:
            fields.append("arbiter_response_notes = ?")
            values.append(arbiter_response_notes)
        fields.append("updated_at = ?")
        values.append(_utcnow())
        values.append(request_id)

        with self._connect() as conn:
            conn.execute(
                f"UPDATE requests SET {', '.join(fields)} WHERE request_id = ?",
                values,
            )
        return self.get_request(request_id)

    def poll_requestee_queue(self, requestee_id: str, limit: int = 10) -> list[RequestRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM requests
                WHERE status = 'pending_requestee' AND requestee_id = ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (requestee_id, limit),
            ).fetchall()
            request_ids = [row["request_id"] for row in rows]
            now = _utcnow()
            for request_id in request_ids:
                conn.execute(
                    """
                    UPDATE requests
                    SET status = 'in_progress', updated_at = ?
                    WHERE request_id = ?
                    """,
                    (now, request_id),
                )
        return [self.get_request(request_id) for request_id in request_ids]

    def poll_requestor_responses(self, requestor_id: str, limit: int = 10) -> list[RequestRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM requests
                WHERE status = 'completed' AND requestor_id = ?
                ORDER BY updated_at ASC
                LIMIT ?
                """,
                (requestor_id, limit),
            ).fetchall()
            request_ids = [row["request_id"] for row in rows]
            now = _utcnow()
            for request_id in request_ids:
                conn.execute(
                    """
                    UPDATE requests
                    SET status = 'delivered', updated_at = ?
                    WHERE request_id = ?
                    """,
                    (now, request_id),
                )
        return [self.get_request(request_id) for request_id in request_ids]

    def enqueue_review(
        self,
        *,
        request_id: str,
        review_type: str,
        reason: str,
        payload_snapshot: dict[str, Any],
    ) -> ReviewItem:
        review_id = str(uuid.uuid4())
        now = _utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO review_queue (
                    id, request_id, review_type, reason, payload_snapshot,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    request_id,
                    review_type,
                    reason,
                    json.dumps(payload_snapshot),
                    "pending",
                    now,
                    now,
                ),
            )
        return self.get_review(review_id)

    def get_review(self, review_id: str) -> ReviewItem:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_queue WHERE id = ?",
                (review_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown review_id: {review_id}")
        return self._row_to_review(row)

    def list_pending_reviews(self, limit: int = 50) -> list[ReviewItem]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM review_queue
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_review(row) for row in rows]

    def resolve_review(
        self,
        review_id: str,
        *,
        approved: bool,
        reviewer_id: str,
        reviewer_notes: str | None = None,
    ) -> ReviewItem:
        review = self.get_review(review_id)
        if review.status != "pending":
            raise ValueError(f"Review item is not pending: {review_id}")

        now = _utcnow()
        status = "approved" if approved else "rejected"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE review_queue
                SET status = ?, reviewer_id = ?, reviewer_notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, reviewer_id, reviewer_notes, now, review_id),
            )

        request = self.get_request(review.request_id)
        if review.review_type == "request":
            if approved:
                self.update_request(review.request_id, status="pending_requestee")
            else:
                self.update_request(review.request_id, status="rejected")
        elif review.review_type == "response":
            if approved:
                self.update_request(
                    review.request_id,
                    status="completed",
                    response_payload=review.payload_snapshot,
                )
            else:
                self.update_request(review.request_id, status="rejected")

        return self.get_review(review_id)
