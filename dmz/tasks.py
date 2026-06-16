"""Celery tasks for request/response validation pipeline."""

from __future__ import annotations

import json
import logging
from typing import Any

from dmz.arbiter import check_request, check_response
from dmz.celery_app import celery_app
from dmz.schemas import SchemaRegistry
from dmz.storage import Storage
from llm_logging import get_logger

logger = get_logger("tasks")


def _send_to_review(
    storage: Storage,
    *,
    request_id: str,
    review_type: str,
    reason: str,
    payload_snapshot: dict[str, Any],
) -> None:
    storage.enqueue_review(
        request_id=request_id,
        review_type=review_type,
        reason=reason,
        payload_snapshot=payload_snapshot,
    )
    storage.update_request(request_id, status=f"pending_review_{review_type}")


@celery_app.task(name="dmz.process_request")
def process_request(request_id: str) -> dict[str, str]:
    storage = Storage()
    schemas = SchemaRegistry()
    record = storage.get_request(request_id)

    try:
        schemas.validate_request(record.schema_id, record.request_payload)
    except Exception as exc:  # noqa: BLE001
        reason = f"Schema validation failed: {exc}"
        logger.warning("Request schema validation failed request_id=%s error=%s", request_id, exc)
        _send_to_review(
            storage,
            request_id=request_id,
            review_type="request",
            reason=reason,
            payload_snapshot=record.request_payload,
        )
        storage.update_request(request_id, validation_errors=reason)
        return {"status": "pending_review_request", "reason": reason}

    try:
        verdict = check_request(record.schema_id, record.request_payload)
    except Exception as exc:  # noqa: BLE001
        reason = f"Arbiter error: {exc}"
        logger.exception("Request arbiter failed request_id=%s", request_id)
        _send_to_review(
            storage,
            request_id=request_id,
            review_type="request",
            reason=reason,
            payload_snapshot=record.request_payload,
        )
        storage.update_request(request_id, arbiter_request_notes=reason)
        return {"status": "pending_review_request", "reason": reason}

    if verdict["approved"]:
        storage.update_request(
            request_id,
            status="pending_requestee",
            arbiter_request_notes=verdict["reason"],
        )
        logger.info("Request approved request_id=%s", request_id)
        return {"status": "pending_requestee", "reason": verdict["reason"]}

    reason = f"Arbiter rejected request: {verdict['reason']}"
    _send_to_review(
        storage,
        request_id=request_id,
        review_type="request",
        reason=reason,
        payload_snapshot=record.request_payload,
    )
    storage.update_request(request_id, arbiter_request_notes=verdict["reason"])
    return {"status": "pending_review_request", "reason": reason}


@celery_app.task(name="dmz.process_response")
def process_response(request_id: str, response_payload: dict[str, Any]) -> dict[str, str]:
    storage = Storage()
    schemas = SchemaRegistry()
    record = storage.get_request(request_id)

    try:
        schemas.validate_response(record.schema_id, response_payload)
    except Exception as exc:  # noqa: BLE001
        reason = f"Schema validation failed: {exc}"
        logger.warning("Response schema validation failed request_id=%s error=%s", request_id, exc)
        _send_to_review(
            storage,
            request_id=request_id,
            review_type="response",
            reason=reason,
            payload_snapshot=response_payload,
        )
        storage.update_request(request_id, validation_errors=reason)
        return {"status": "pending_review_response", "reason": reason}

    try:
        pair = schemas.get(record.schema_id)
        verdict = check_response(
            record.schema_id,
            record.request_payload,
            response_payload,
            response_schema=pair.response_schema,
            operation_description=pair.binding.description,
        )
    except Exception as exc:  # noqa: BLE001
        reason = f"Arbiter error: {exc}"
        logger.exception("Response arbiter failed request_id=%s", request_id)
        _send_to_review(
            storage,
            request_id=request_id,
            review_type="response",
            reason=reason,
            payload_snapshot=response_payload,
        )
        storage.update_request(request_id, arbiter_response_notes=reason)
        return {"status": "pending_review_response", "reason": reason}

    if verdict["approved"]:
        storage.update_request(
            request_id,
            status="completed",
            response_payload=response_payload,
            arbiter_response_notes=verdict["reason"],
        )
        logger.info("Response approved request_id=%s", request_id)
        return {"status": "completed", "reason": verdict["reason"]}

    reason = f"Arbiter rejected response: {verdict['reason']}"
    _send_to_review(
        storage,
        request_id=request_id,
        review_type="response",
        reason=reason,
        payload_snapshot=response_payload,
    )
    storage.update_request(request_id, arbiter_response_notes=verdict["reason"])
    return {"status": "pending_review_response", "reason": reason}
