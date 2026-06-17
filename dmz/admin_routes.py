"""Admin web UI routes for the A2A DMZ gateway."""

from __future__ import annotations

import json
import os
from functools import wraps
from html import escape
from typing import Any, Callable

from flask import Flask, Response, redirect, render_template, request, session, url_for

from dmz.agents import AgentRegistry, AuthError
from dmz.schemas import SchemaRegistry
from dmz.storage import RequestRecord, ReviewItem, Storage
from llm_logging import get_logger

logger = get_logger("admin")

SESSION_AGENT_KEY = "admin_agent_id"


def _is_datastar_request() -> bool:
    return request.headers.get("Datastar-Request") == "true"


def _read_login_credentials() -> tuple[str | None, str | None]:
    """Accept credentials from Datastar signals, form posts, or JSON bodies."""
    if request.form.get("agent_id") or request.form.get("agent_key"):
        return request.form.get("agent_id"), request.form.get("agent_key")

    data = request.get_json(silent=True)
    if isinstance(data, dict):
        nested = data.get("signals")
        if isinstance(nested, dict):
            data = {**data, **nested}
        agent_id = data.get("agentId") or data.get("agent_id")
        agent_key = data.get("agentKey") or data.get("agent_key")
        if agent_id or agent_key:
            return agent_id, agent_key

    return None, None


def _datastar_redirect(location: str) -> Response:
    return Response(
        f'<script type="text/javascript">window.location.assign({json.dumps(location)});</script>',
        mimetype="text/html",
    )


def _pretty_json(data: Any) -> str:
    # quote=False: keep " in JSON readable inside <pre><code>; still escape <>&.
    return escape(json.dumps(data, indent=2, default=str), quote=False)


def _read_datastar_signals() -> dict[str, Any]:
    """Read Datastar signals from GET query param or JSON request body."""
    raw = request.args.get("datastar")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    data = request.get_json(silent=True)
    if isinstance(data, dict):
        signals = data.get("signals")
        if isinstance(signals, dict):
            return signals
        return data
    return {}


def _expanded_request(storage: Storage) -> tuple[str | None, RequestRecord | None]:
    detail_id = _read_datastar_signals().get("detailRequestId")
    if not detail_id:
        return None, None
    detail_id = str(detail_id)
    try:
        return detail_id, storage.get_request(detail_id)
    except KeyError:
        return detail_id, None


def register_admin_routes(
    app: Flask,
    *,
    agent_registry: AgentRegistry,
    schema_registry: SchemaRegistry,
    storage: Storage,
) -> None:
    secret = os.getenv("FLASK_SECRET_KEY", "dev-admin-secret-change-me")
    app.secret_key = secret

    def require_admin(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            if SESSION_AGENT_KEY not in session:
                if request.path.startswith("/admin/partials"):
                    return Response("Unauthorized", status=401)
                return redirect(url_for("admin_login"))
            return view(*args, **kwargs)

        return wrapped

    def current_reviewer_id() -> str:
        agent_id = session.get(SESSION_AGENT_KEY)
        if not agent_id:
            raise AuthError("Not authenticated")
        key = session.get(f"admin_key_{agent_id}")
        if not key:
            raise AuthError("Session expired")
        context = agent_registry.authenticate(agent_id, key)
        agent_registry.require_role(context, "reviewer")
        return context.agent_id

    @app.get("/admin/login")
    def admin_login():
        if SESSION_AGENT_KEY in session:
            return redirect(url_for("admin_dashboard"))
        return render_template("admin/login.html")

    @app.post("/admin/login")
    def admin_login_post():
        agent_id, agent_key = _read_login_credentials()

        try:
            context = agent_registry.authenticate(agent_id, agent_key)
            agent_registry.require_role(context, "reviewer")
        except AuthError as exc:
            if _is_datastar_request():
                return render_template("admin/partials/login_error.html", error=str(exc)), 401
            return render_template("admin/login.html", error=str(exc)), 401

        session[SESSION_AGENT_KEY] = context.agent_id
        session[f"admin_key_{context.agent_id}"] = agent_key
        session.permanent = True
        logger.info("Admin login agent=%s", context.agent_id)
        dashboard_url = url_for("admin_dashboard")
        if _is_datastar_request():
            return _datastar_redirect(dashboard_url)
        return redirect(dashboard_url)

    @app.post("/admin/logout")
    @require_admin
    def admin_logout():
        agent_id = session.pop(SESSION_AGENT_KEY, None)
        if agent_id:
            session.pop(f"admin_key_{agent_id}", None)
        login_url = url_for("admin_login")
        if _is_datastar_request():
            return _datastar_redirect(login_url)
        return redirect(login_url)

    @app.get("/admin")
    @require_admin
    def admin_dashboard():
        return render_template("admin/dashboard.html", agent_id=session[SESSION_AGENT_KEY])

    @app.get("/admin/partials/stats")
    @require_admin
    def admin_stats():
        return render_template(
            "admin/partials/stats.html",
            inflight=len(storage.list_inflight_requests(limit=500)),
            pending_reviews=len(storage.list_pending_reviews(limit=500)),
            schema_count=len(schema_registry.list_schemas()),
            counts=storage.count_requests_by_status(),
        )

    @app.get("/admin/partials/schemas")
    @require_admin
    def admin_schemas():
        return render_template(
            "admin/partials/schemas.html",
            schemas=schema_registry.list_schemas_detail(),
            pretty_json=_pretty_json,
        )

    @app.get("/admin/partials/inflight")
    @require_admin
    def admin_inflight():
        expanded_id, expanded_record = _expanded_request(storage)
        return render_template(
            "admin/partials/request_table.html",
            records=storage.list_inflight_requests(),
            title="In-flight requests",
            empty_message="No requests currently in flight.",
            list_partial="/admin/partials/inflight",
            expanded_request_id=expanded_id,
            expanded_record=expanded_record,
            pretty_json=_pretty_json,
        )

    @app.get("/admin/partials/log")
    @require_admin
    def admin_log():
        expanded_id, expanded_record = _expanded_request(storage)
        return render_template(
            "admin/partials/request_table.html",
            records=storage.list_requests(limit=100, exclude_inflight=True),
            title="Access log",
            empty_message="No completed or historical requests yet.",
            list_partial="/admin/partials/log",
            expanded_request_id=expanded_id,
            expanded_record=expanded_record,
            pretty_json=_pretty_json,
        )

    @app.get("/admin/partials/reviews")
    @require_admin
    def admin_reviews():
        expanded_id, expanded_record = _expanded_request(storage)
        return render_template(
            "admin/partials/reviews.html",
            reviews=storage.list_pending_reviews(limit=100),
            expanded_request_id=expanded_id,
            expanded_record=expanded_record,
            pretty_json=_pretty_json,
        )

    @app.get("/admin/partials/request-detail-clear/<request_id>")
    @require_admin
    def admin_request_detail_clear(request_id: str):
        return render_template("admin/partials/request_detail_clear.html", request_id=request_id)

    @app.get("/admin/partials/request/<request_id>")
    @require_admin
    def admin_request_detail(request_id: str):
        try:
            record = storage.get_request(request_id)
        except KeyError:
            return Response("Request not found", status=404)
        return render_template(
            "admin/partials/request_detail.html",
            record=record,
            pretty_json=_pretty_json,
        )

    @app.post("/admin/review/<review_id>/approve")
    @require_admin
    def admin_approve_review(review_id: str):
        reviewer_id = current_reviewer_id()
        data = request.get_json(silent=True) or {}
        notes = data.get("notes") or data.get("reviewNotes") or request.form.get("notes")
        storage.resolve_review(
            review_id,
            approved=True,
            reviewer_id=reviewer_id,
            reviewer_notes=notes,
        )
        logger.info("Admin approved review_id=%s reviewer=%s", review_id, reviewer_id)
        return _multi_patch(storage)

    @app.post("/admin/review/<review_id>/reject")
    @require_admin
    def admin_reject_review(review_id: str):
        reviewer_id = current_reviewer_id()
        data = request.get_json(silent=True) or {}
        notes = data.get("notes") or data.get("reviewNotes") or request.form.get("notes")
        storage.resolve_review(
            review_id,
            approved=False,
            reviewer_id=reviewer_id,
            reviewer_notes=notes,
        )
        logger.info("Admin rejected review_id=%s reviewer=%s", review_id, reviewer_id)
        return _multi_patch(storage)

    def _multi_patch(storage: Storage) -> Response:
        expanded_id, expanded_record = _expanded_request(storage)
        html = (
            render_template(
                "admin/partials/reviews.html",
                reviews=storage.list_pending_reviews(limit=100),
                expanded_request_id=expanded_id,
                expanded_record=expanded_record,
                pretty_json=_pretty_json,
            )
            + render_template(
                "admin/partials/stats.html",
                inflight=len(storage.list_inflight_requests(limit=500)),
                pending_reviews=len(storage.list_pending_reviews(limit=500)),
                schema_count=len(schema_registry.list_schemas()),
                counts=storage.count_requests_by_status(),
            )
        )
        return Response(html, mimetype="text/html")
