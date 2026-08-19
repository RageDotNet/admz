"""Agent-facing REST API v2 (`rest-api-v2.md`)."""

from __future__ import annotations

import pathlib
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request
from sqlalchemy import select

from llmdmz.core.auth import Identity, bearer_token, resolve_bearer
from llmdmz.core.db import session_scope
from llmdmz.core.models import Action, ActionVersion, Agent, Enrollment

bp = Blueprint("api_v2", __name__, url_prefix="/v2")


# --- helpers -----------------------------------------------------------------


def error(code: str, message: str, status: int, detail: Any = None) -> tuple[Response, int]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail is not None:
        body["error"]["detail"] = detail
    return jsonify(body), status


class ApiError(Exception):
    """Carries an error envelope through to the Flask error handler."""

    def __init__(self, code: str, message: str, status: int, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.detail = detail


def parse_json_body() -> dict[str, Any]:
    if not request.is_json:
        raise ApiError("malformed_json", "Request body must be JSON.", 400)
    try:
        body = request.get_json()
    except Exception:  # noqa: BLE001 â€” Flask raises varied parse errors
        raise ApiError("malformed_json", "Request body is not valid JSON.", 400) from None
    if not isinstance(body, dict):
        raise ApiError("malformed_json", "Request body must be a JSON object.", 400)
    return body


def authenticate() -> Identity:
    token = bearer_token()
    if token is None:
        raise ApiError("unauthorized", "Missing bearer key.", 401)
    with session_scope(current_app) as session:
        identity = resolve_bearer(session, current_app.config["DMZ"], token)
    if identity is None:
        raise ApiError("unauthorized", "Unknown or revoked bearer key.", 401)
    return identity


def authenticate_agent() -> Agent:
    """Authenticate and require an agent (admin tokens are 403 on /v2, #17)."""
    identity = authenticate()
    if identity.kind != "agent" or identity.agent is None:
        raise ApiError("forbidden", "Admin tokens are not valid on /v2 endpoints.", 403)
    return identity.agent


def require_provider(agent: Agent) -> None:
    if not agent.is_provider:
        raise ApiError("forbidden", "This endpoint requires the provider capability.", 403)


def require_client(agent: Agent) -> None:
    if not agent.is_client:
        raise ApiError("forbidden", "This endpoint requires the client capability.", 403)


def validate_and_compile(body: dict[str, Any]) -> dict[str, Any]:
    """Field-validate + compile a schema package; raises 422 ApiError on failure."""
    from llmdmz.registry import compile_schemas, validate_submission

    validation = validate_submission(body)
    if not validation.ok or validation.normalized is None:
        raise ApiError(
            "request_schema_invalid",
            "Submission failed field validation.",
            422,
            validation.as_detail(),
        )
    compile_issues = compile_schemas(validation.normalized)
    if compile_issues:
        raise ApiError(
            "request_schema_invalid",
            "Schemas failed to compile.",
            422,
            {"issues": [{"field": i.field, "message": i.message} for i in compile_issues]},
        )
    return validation.normalized


# --- T2.4: POST /v2/actions ----------------------------------------------------


@bp.post("/actions")
def create_action():
    agent = authenticate_agent()
    require_provider(agent)
    payload = validate_and_compile(parse_json_body())

    from llmdmz.core import storage
    from llmdmz.core.audit import audit

    with session_scope(current_app) as session:
        if storage.get_action(session, payload["id"]) is not None:
            raise ApiError("duplicate_action", f"Action '{payload['id']}' already exists.", 409)
        owner = session.get(Agent, agent.id)
        assert owner is not None
        action = Action(id=payload["id"], owner_agent_id=owner.id, state="pending")
        session.add(action)
        session.flush()
        version = ActionVersion(
            action_id=action.id, version_number=1, state="submitted", payload=payload
        )
        session.add(version)
        session.flush()
        audit(
            session,
            actor_type="agent",
            actor_id=owner.id,
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

# --- T2.5: GET /v2/actions/{id} (role-projected views) --------------------------


def _client_view(action: Action, active: ActionVersion, enrollment_state: str) -> dict:
    payload = active.payload
    return {
        "id": action.id,
        "state": action.state,
        "active_version": active.version_number,
        "description": payload.get("description", ""),
        "request_schema": payload.get("request_schema"),
        "response_schema": payload.get("response_schema"),
        "client_instructions": payload.get("client_instructions", ""),
        "enrollment": enrollment_state,
    }


def _owner_view(action: Action, active: ActionVersion | None) -> dict:
    payload = active.payload if active else {}
    return {
        "id": action.id,
        "state": action.state,
        "active_version": active.version_number if active else None,
        "description": payload.get("description", ""),
        "request_schema": payload.get("request_schema"),
        "response_schema": payload.get("response_schema"),
        "request_arbiter_instructions": payload.get("request_arbiter_instructions", ""),
        "response_arbiter_instructions": payload.get("response_arbiter_instructions", ""),
        "client_instructions": payload.get("client_instructions", ""),
        "provider_instructions": payload.get("provider_instructions", ""),
    }


@bp.get("/actions/<action_id>")
def get_action_detail(action_id: str):
    agent = authenticate_agent()

    from llmdmz.core import storage

    with session_scope(current_app) as session:
        action = storage.get_action(session, action_id)
        if action is None:
            raise ApiError("not_found", "Unknown action.", 404)
        active = action.active_version
        if agent.is_provider and action.owner_agent_id == agent.id:
            return jsonify(_owner_view(action, active))
        if not agent.is_client:
            # A provider looking at someone else's action: not visible.
            raise ApiError("not_found", "Unknown action.", 404)
        if active is None or action.state != "active":
            # Never-approved / withdrawn actions are hidden from clients (404, #10).
            raise ApiError("not_found", "Unknown action.", 404)
        enrollment = storage.find_enrollment(session, agent_id=agent.id, action_id=action.id)
        enrollment_state = enrollment.state if enrollment else "available"
        return jsonify(_client_view(action, active, enrollment_state))


# --- T2.6: PUT /v2/actions/<id> (submit new version) + version history ----------


@bp.put("/actions/<action_id>")
def submit_new_version(action_id: str):
    agent = authenticate_agent()
    require_provider(agent)
    body = parse_json_body()
    if body.get("id") != action_id:
        raise ApiError(
            "request_schema_invalid",
            "The submission id must match the action id in the URL.",
            422,
            {"field": "id"},
        )
    payload = validate_and_compile(body)

    from llmdmz.core import storage
    from llmdmz.core.audit import audit
    from llmdmz.core.models import ActionVersion

    with session_scope(current_app) as session:
        action = storage.get_action(session, action_id)
        if action is None or action.owner_agent_id != agent.id:
            raise ApiError("not_found", "Unknown action.", 404)
        pending = (
            session.query(ActionVersion)
            .filter(ActionVersion.action_id == action.id, ActionVersion.state == "submitted")
            .one_or_none()
        )
        if pending is not None:
            raise ApiError(
                "version_pending",
                "A version is already pending review for this action.",
                409,
                {
                    "pending_version_id": str(pending.id),
                    "pending_version_number": pending.version_number,
                },
            )
        last = (
            session.query(ActionVersion)
            .filter(ActionVersion.action_id == action.id)
            .order_by(ActionVersion.version_number.desc())
            .first()
        )
        next_number = (last.version_number + 1) if last else 1
        version = ActionVersion(
            action_id=action.id, version_number=next_number, state="submitted", payload=payload
        )
        session.add(version)
        session.flush()
        audit(
            session,
            actor_type="agent",
            actor_id=agent.id,
            event="action.version_submitted",
            target_type="action_version",
            target_id=str(version.id),
            detail={"action_id": action.id, "version_number": next_number},
        )
        return (
            jsonify(
                {
                    "id": action.id,
                    "state": action.state,
                    "version": {"number": next_number, "state": "submitted"},
                    "notice": "version_pending",
                }
            ),
            201,
        )


@bp.get("/actions/<action_id>/versions")
def list_versions(action_id: str):
    agent = authenticate_agent()
    require_provider(agent)
    with session_scope(current_app) as session:
        from llmdmz.core import storage

        action = storage.get_action(session, action_id)
        if action is None or action.owner_agent_id != agent.id:
            raise ApiError("not_found", "Unknown action.", 404)
        versions = sorted(action.versions, key=lambda v: v.version_number)
        return jsonify(
            {
                "id": action.id,
                "versions": [
                    {
                        "number": v.version_number,
                        "state": v.state,
                        "submitted_at": v.submitted_at.isoformat() if v.submitted_at else None,
                        "payload": v.payload,
                    }
                    for v in versions
                ],
            }
        )


# --- T2.7: DELETE /v2/actions/<id> (soft withdraw) -------------------------------


@bp.delete("/actions/<action_id>")
def withdraw_action(action_id: str):
    agent = authenticate_agent()
    require_provider(agent)
    with session_scope(current_app) as session:
        from llmdmz.core import storage
        from llmdmz.core.audit import audit

        action = storage.get_action(session, action_id)
        if action is None or action.owner_agent_id != agent.id:
            raise ApiError("not_found", "Unknown action.", 404)
        action.state = "withdrawn"
        session.flush()
        audit(
            session,
            actor_type="agent",
            actor_id=agent.id,
            event="action.withdrawn",
            target_type="action",
            target_id=action.id,
        )
        return jsonify({"id": action.id, "state": action.state})


# --- T2.10/T2.11: GET /v2/actions (role-projected directory, #18-#20) ----------


def _clamp_int(value: str | None, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value) if value is not None else default
    except ValueError:
        return default
    return max(lo, min(hi, n))


@bp.get("/actions")
def list_actions():
    agent = authenticate_agent()
    page = _clamp_int(request.args.get("page"), 1, 1, 10**9)
    per_page = _clamp_int(request.args.get("per_page"), 100, 1, 500)
    q = (request.args.get("q") or "").strip().lower()
    enrollment_filter = request.args.get("enrollment") or None

    from llmdmz.core import storage
    from llmdmz.core.models import Action

    with session_scope(current_app) as session:
        # Provider-only agents see only their own actions (provider projection).
        rows = session.scalars(select(Action).order_by(Action.id)).all()
        if agent.is_client:
            visible = rows  # full client projection incl. other providers (#20)
        else:
            visible = [a for a in rows if a.owner_agent_id == agent.id]
        enrollments = {
            e.action_id: e.state
            for e in session.scalars(
                select(Enrollment).where(Enrollment.agent_id == agent.id)
            ).all()
        }
        items = []
        for action in visible:
            active = action.active_version
            if agent.is_client:
                if active is not None and action.state == "active":
                    state = enrollments.get(action.id, "available")
                else:
                    state = "unavailable"  # display-only (#10)
            else:
                state = action.state  # provider projection: canonical state
            payload = active.payload if active else {}
            entry = {
                "id": action.id,
                "description": payload.get("description", "")[0:200] if payload else "",
                "state": state if not agent.is_client else action.state,
                "enrollment": enrollments.get(action.id, "available") if agent.is_client else None,
                "active_version": active.version_number if active else None,
            }
            if agent.is_client:
                entry["state"] = state  # client-relative annotation in `state`
            # Provider overlay on owned rows (dual-role merge base, #19).
            if agent.is_provider and action.owner_agent_id == agent.id:
                entry["owner"] = True
                entry["action_state"] = action.state
                pending = storage.submitted_version(session, action.id)
                entry["pending_version"] = pending.version_number if pending else None
            items.append((action, entry))
        # Compose filters: q substring + enrollment (#18).
        result = [
            entry
            for action, entry in items
            if _matches(action, entry, q, enrollment_filter)
        ]
        total = len(result)
        start = (page - 1) * per_page
        return jsonify(
            {
                "items": result[start : start + per_page],
                "page": page,
                "per_page": per_page,
                "total": total,
            }
        )


def _matches(action, entry, q, enrollment_filter):
    if q and q not in action.id.lower() and q not in entry["description"].lower():
        return False
    if enrollment_filter and entry.get("enrollment") != enrollment_filter:
        return False
    return True


# --- T2.13: POST/GET /v2/actions/<id>/enroll -------------------------------------


@bp.post("/actions/<action_id>/enroll")
def request_enrollment(action_id: str):
    agent = authenticate_agent()
    require_client(agent)
    with session_scope(current_app) as session:
        from llmdmz.core import storage
        from llmdmz.core.audit import audit
        from llmdmz.core.models import Enrollment

        action = storage.get_action(session, action_id)
        # Enrollment only against listed, invokable actions (#10).
        if action is None or action.state != "active" or action.active_version is None:
            raise ApiError("not_found", "Unknown action.", 404)
        existing = storage.find_enrollment(session, agent_id=agent.id, action_id=action.id)
        if existing is not None and existing.state in ("requested", "enrolled"):
            raise ApiError("already_enrolled", "An enrollment already exists.", 409)
        enrollment = Enrollment(agent_id=agent.id, action_id=action.id, state="requested")
        session.add(enrollment)
        session.flush()
        audit(
            session,
            actor_type="agent",
            actor_id=agent.id,
            event="enrollment.requested",
            target_type="enrollment",
            target_id=str(enrollment.id),
            detail={"action_id": action.id},
        )
        return (
            jsonify(
                {
                    "action": action.id,
                    "state": enrollment.state,
                    "requested_at": enrollment.requested_at.isoformat()
                    if enrollment.requested_at
                    else None,
                }
            ),
            201,
        )


@bp.get("/actions/<action_id>/enroll")
def enrollment_state(action_id: str):
    agent = authenticate_agent()
    require_client(agent)
    with session_scope(current_app) as session:
        from llmdmz.core import storage

        action = storage.get_action(session, action_id)
        if action is None:
            raise ApiError("not_found", "Unknown action.", 404)
        enrollment = storage.find_enrollment(session, agent_id=agent.id, action_id=action.id)
        if enrollment is None:
            raise ApiError("not_found", "No enrollment exists for this action.", 404)
        return jsonify(
            {
                "action": action.id,
                "state": enrollment.state,
                "requested_at": enrollment.requested_at.isoformat()
                if enrollment.requested_at
                else None,
                "granted_at": enrollment.decided_at.isoformat()
                if enrollment.state == "enrolled" and enrollment.decided_at
                else None,
            }
        )


# --- T2.16: GET /v2/skill (role-merged skill documents, #21) ---------------------

_SKILLS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "skills"


def _load_skill(name: str) -> str:
    path = _SKILLS_DIR / name
    return path.read_text(encoding="utf-8")


@bp.get("/skill")
def skill():
    agent = authenticate_agent()
    documents = []
    if agent.is_client:
        documents.append(_load_skill("client.md"))
    if agent.is_provider:
        documents.append(_load_skill("provider.md"))
    if not documents:
        raise ApiError("forbidden", "No skill applies to this agent.", 403)
    return jsonify(
        {
            "base_url": "",
            "capabilities": {"is_client": agent.is_client, "is_provider": agent.is_provider},
            "skill": "\n\n---\n\n".join(documents),
        }
    )
