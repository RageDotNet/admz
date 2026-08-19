"""Agent-facing REST API v2 (`rest-api-v2.md`)."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request

from llmdmz.core.auth import Identity, bearer_token, resolve_bearer
from llmdmz.core.db import session_scope
from llmdmz.core.models import Agent

bp = Blueprint("api_v2", __name__, url_prefix="/v2")


# --- helpers -----------------------------------------------------------------


def error(code: str, message: str, status: int, detail: Any = None) -> tuple[Response, int]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return jsonify(body), status


def parse_json_body() -> tuple[dict[str, Any] | None, tuple[Response, int] | None]:
    if not request.is_json:
        return None, error("malformed_json", "Request body must be JSON.", 400)
    try:
        body = request.get_json()
    except Exception:  # noqa: BLE001 — Flask raises varied parse errors
        return None, error("malformed_json", "Request body is not valid JSON.", 400)
    if not isinstance(body, dict):
        return None, error("malformed_json", "Request body must be a JSON object.", 400)
    return body, None


def authenticate() -> tuple[Identity | None, tuple[Response, int] | None]:
    token = bearer_token()
    if token is None:
        return None, error("unauthorized", "Missing bearer key.", 401)
    with session_scope(current_app) as session:
        identity = resolve_bearer(session, current_app.config["DMZ"], token)
    if identity is None:
        return None, error("unauthorized", "Unknown or revoked bearer key.", 401)
    return identity, None


def require_provider(identity: Identity) -> tuple[Response, int] | None:
    if identity.kind != "agent" or not (identity.agent and identity.agent.is_provider):
        return error("forbidden", "This endpoint requires the provider capability.", 403)
    return None


def require_client(identity: Identity) -> tuple[Response, int] | None:
    if identity.kind != "agent" or not (identity.agent and identity.agent.is_client):
        return error("forbidden", "This endpoint requires the client capability.", 403)
    return None


# --- T2.4: POST /v2/actions ----------------------------------------------------


@bp.post("/actions")
def create_action():
    identity, err = authenticate()
    if err:
        return err
    err = require_provider(identity)
    if err:
        return err
    assert identity.agent is not None
    body, err = parse_json_body()
    if err or body is None:
        assert err is not None
        return err

    from llmdmz.registry import compile_schemas, validate_submission

    validation = validate_submission(body)
    if not validation.ok or validation.normalized is None:
        return error(
            "request_schema_invalid",
            "Submission failed field validation.",
            422,
            validation.as_detail(),
        )
    compile_issues = compile_schemas(validation.normalized)
    if compile_issues:
        return error(
            "request_schema_invalid",
            "Schemas failed to compile.",
            422,
            {"issues": [{"field": i.field, "message": i.message} for i in compile_issues]},
        )

    payload = validation.normalized
    from llmdmz.core import storage
    from llmdmz.core.audit import audit
    from llmdmz.core.models import Action, ActionVersion

    with session_scope(current_app) as session:
        if storage.get_action(session, payload["id"]) is not None:
            return error(
                "duplicate_action", f"Action '{payload['id']}' already exists.", 409
            )
        agent = session.get(Agent, identity.agent.id)
        assert agent is not None
        action = Action(id=payload["id"], owner_agent_id=agent.id, state="pending")
        session.add(action)
        session.flush()
        version = ActionVersion(
            action_id=action.id,
            version_number=1,
            state="submitted",
            payload=payload,
        )
        session.add(version)
        session.flush()
        audit(
            session,
            actor_type="agent",
            actor_id=agent.id,
            event="action.created",
            target_type="action",
            target_id=action.id,
            detail={"version_number": 1},
        )
        return (
            jsonify(
                {
                    "id": action.id,
                    "state": action.state,
                    "version": {"number": 1, "state": "submitted"},
                }
            ),
            201,
        )
