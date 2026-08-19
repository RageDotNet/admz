"""LLM DMZ HTTP service."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from dmz.agents import AgentRegistry, AuthContext, AuthError
from dmz.schemas import SchemaRegistry
from dmz.storage import RequestRecord, Storage
from dmz.tasks import process_request, process_response
from llm_logging import get_logger

load_dotenv()

logger = get_logger("server")

app = Flask(__name__)
agent_registry = AgentRegistry()
schema_registry = SchemaRegistry()
storage = Storage()


def _auth() -> AuthContext:
    return agent_registry.authenticate(
        request.headers.get("X-Agent-Id"),
        request.headers.get("X-Agent-Key"),
    )


def _request_json() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object body")
    return data


def _serialize_request(record: RequestRecord) -> dict[str, Any]:
    return {
        "request_id": record.request_id,
        "schema_id": record.schema_id,
        "requestor_id": record.requestor_id,
        "requestee_id": record.requestee_id,
        "status": record.status,
        "request_payload": record.request_payload,
        "response_payload": record.response_payload,
        "validation_errors": record.validation_errors,
        "arbiter_request_notes": record.arbiter_request_notes,
        "arbiter_response_notes": record.arbiter_response_notes,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


@app.errorhandler(AuthError)
def _auth_error(exc: AuthError):
    return jsonify({"error": str(exc)}), 401


@app.errorhandler(KeyError)
def _not_found(exc: KeyError):
    return jsonify({"error": str(exc)}), 404


@app.errorhandler(ValueError)
def _bad_request(exc: ValueError):
    return jsonify({"error": str(exc)}), 400


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/v1/schemas")
def list_schemas():
    _auth()
    return jsonify({"schemas": schema_registry.list_schemas()})


@app.post("/api/v1/requests")
def submit_request():
    auth = _auth()
    agent_registry.require_role(auth, "requestor")
    body = _request_json()

    schema_id = body.get("schema_id")
    request_id = body.get("request_id")
    payload = body.get("payload")
    if not schema_id or not request_id or not isinstance(payload, dict):
        raise ValueError("schema_id, request_id, and payload object are required")

    binding = schema_registry.get(schema_id).binding
    if binding.requestor_id != auth.agent_id:
        raise AuthError("Requestor is not authorized for this schema")

    logger.info(
        "Request submitted request_id=%s schema_id=%s requestor=%s",
        request_id,
        schema_id,
        auth.agent_id,
    )

    try:
        storage.get_request(request_id)
        raise ValueError(f"request_id already exists: {request_id}")
    except KeyError:
        pass

    record = storage.create_request(
        request_id=request_id,
        schema_id=schema_id,
        requestor_id=auth.agent_id,
        requestee_id=binding.requestee_id,
        request_payload=payload,
    )
    process_request.delay(request_id)
    return jsonify({"request": _serialize_request(record)}), 202


@app.get("/api/v1/requests/poll")
def poll_requests():
    auth = _auth()
    agent_registry.require_role(auth, "requestee")
    limit = min(int(request.args.get("limit", 10)), 100)
    records = storage.poll_requestee_queue(auth.agent_id, limit=limit)
    logger.info("Requestee poll agent=%s count=%d", auth.agent_id, len(records))
    return jsonify({"requests": [_serialize_request(record) for record in records]})


@app.post("/api/v1/requests/<request_id>/response")
def submit_response(request_id: str):
    auth = _auth()
    agent_registry.require_role(auth, "requestee")
    body = _request_json()
    payload = body.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload object is required")

    record = storage.get_request(request_id)
    if record.requestee_id != auth.agent_id:
        raise AuthError("Requestee is not authorized for this request")
    if record.status not in {"in_progress", "pending_requestee"}:
        raise ValueError(f"Request is not ready for response: {record.status}")

    logger.info("Response submitted request_id=%s requestee=%s", request_id, auth.agent_id)
    storage.update_request(request_id, status="validating_response")
    process_response.delay(request_id, payload)
    record = storage.get_request(request_id)
    return jsonify({"request": _serialize_request(record)}), 202


@app.get("/api/v1/responses/poll")
def poll_responses():
    auth = _auth()
    agent_registry.require_role(auth, "requestor")
    limit = min(int(request.args.get("limit", 10)), 100)
    records = storage.poll_requestor_responses(auth.agent_id, limit=limit)
    logger.info("Requestor poll agent=%s count=%d", auth.agent_id, len(records))
    return jsonify({"responses": [_serialize_request(record) for record in records]})


@app.get("/api/v1/requests/<request_id>")
def get_request_status(request_id: str):
    auth = _auth()
    record = storage.get_request(request_id)
    if auth.agent_id not in {record.requestor_id, record.requestee_id}:
        agent_registry.require_role(auth, "reviewer")
    return jsonify({"request": _serialize_request(record)})


@app.get("/api/v1/review/pending")
def list_reviews():
    auth = _auth()
    agent_registry.require_role(auth, "reviewer")
    limit = min(int(request.args.get("limit", 50)), 200)
    reviews = storage.list_pending_reviews(limit=limit)
    return jsonify(
        {
            "reviews": [
                {
                    "id": item.id,
                    "request_id": item.request_id,
                    "review_type": item.review_type,
                    "reason": item.reason,
                    "payload_snapshot": item.payload_snapshot,
                    "status": item.status,
                    "created_at": item.created_at,
                }
                for item in reviews
            ]
        }
    )


@app.post("/api/v1/review/<review_id>/approve")
def approve_review(review_id: str):
    auth = _auth()
    agent_registry.require_role(auth, "reviewer")
    body = _request_json()
    notes = body.get("notes")
    item = storage.resolve_review(
        review_id,
        approved=True,
        reviewer_id=auth.agent_id,
        reviewer_notes=notes,
    )
    logger.info("Review approved review_id=%s reviewer=%s", review_id, auth.agent_id)
    record = storage.get_request(item.request_id)
    return jsonify({"review": item.__dict__, "request": _serialize_request(record)})


@app.post("/api/v1/review/<review_id>/reject")
def reject_review(review_id: str):
    auth = _auth()
    agent_registry.require_role(auth, "reviewer")
    body = _request_json()
    notes = body.get("notes")
    item = storage.resolve_review(
        review_id,
        approved=False,
        reviewer_id=auth.agent_id,
        reviewer_notes=notes,
    )
    logger.info("Review rejected review_id=%s reviewer=%s", review_id, auth.agent_id)
    record = storage.get_request(item.request_id)
    return jsonify({"review": item.__dict__, "request": _serialize_request(record)})


def main() -> None:
    host = os.getenv("LLMDMZ_HOST", "127.0.0.1")
    port = int(os.getenv("LLMDMZ_PORT", "8080"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
