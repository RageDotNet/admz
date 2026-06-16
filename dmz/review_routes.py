"""Shared Flask review API routes for DMZ services."""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from dmz.agents import AgentRegistry, AuthContext, AuthError
from dmz.storage import RequestRecord, Storage
from llm_logging import get_logger

logger = get_logger("review_api")


def _auth(agent_registry: AgentRegistry) -> AuthContext:
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


def register_review_routes(
    app: Flask,
    *,
    agent_registry: AgentRegistry,
    storage: Storage,
) -> None:
    @app.errorhandler(AuthError)
    def _auth_error(exc: AuthError):
        return jsonify({"error": str(exc)}), 401

    @app.errorhandler(KeyError)
    def _not_found(exc: KeyError):
        return jsonify({"error": str(exc)}), 404

    @app.errorhandler(ValueError)
    def _bad_request(exc: ValueError):
        return jsonify({"error": str(exc)}), 400

    @app.get("/api/v1/requests/<request_id>")
    def get_request_status(request_id: str):
        auth = _auth(agent_registry)
        record = storage.get_request(request_id)
        if auth.agent_id not in {record.requestor_id, record.requestee_id}:
            agent_registry.require_role(auth, "reviewer")
        return jsonify({"request": _serialize_request(record)})

    @app.get("/api/v1/review/pending")
    def list_reviews():
        auth = _auth(agent_registry)
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
        auth = _auth(agent_registry)
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
        auth = _auth(agent_registry)
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
