"""Admin console (webui-v2.md): auth guard, login/CSRF, SSE merge helper.

The console blueprint is mounted under /admin on the single Flask app. All
routes exactly match the authoritative route table in webui-v2.md (#27).
"""

from __future__ import annotations

import functools
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from datastar_py import ServerSentEventGenerator as SSE
from datastar_py.consts import ElementPatchMode
from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from markupsafe import Markup, escape

from admz.core.auth import bearer_token, resolve_bearer

bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates")

# Domain states/outcomes → Bootstrap 5 `text-bg-*` color.
STATE_TAG = {
    # action states
    "pending": "warning",
    "active": "success",
    "withdrawn": "secondary",
    # version states
    "submitted": "warning",
    "rejected": "danger",
    "superseded": "secondary",
    # enrollment states
    "requested": "info",
    "enrolled": "success",
    "revoked": "secondary",
    "enabled": "success",
    "disabled": "secondary",
    "set": "success",
    # request outcomes (terminal)
    "completed": "success",
    "request_schema_invalid": "warning",
    "arbiter_rejected": "danger",
    "provider_failed": "danger",
    "provider_error": "danger",
    "transport": "danger",
    "timeout": "danger",
    "protocol": "danger",
    "response_schema_invalid": "danger",
    "arbiter_transport": "warning",
    "arbiter_unavailable": "warning",
    "internal_error": "danger",
    # request outcomes (in-flight progress)
    "in_flight": "info",
    "received": "info",
    "arbiter_reviewing_request": "info",
    "dispatching": "primary",
    "arbiter_reviewing_response": "info",
}


def state_tag(state: str) -> str:
    return STATE_TAG.get(state, "secondary")


def state_label(state: str | None) -> str:
    """Sentence-case label: provider_failed → Provider failed."""
    if not state:
        return ""
    words = state.replace("_", " ").split()
    if not words:
        return ""
    return words[0].capitalize() + ((" " + " ".join(words[1:])) if len(words) > 1 else "")


_TRANSPORT_ERROR_CLASSES = frozenset(
    {"transport", "timeout", "protocol", "arbiter_transport"}
)


def log_outcome(req) -> str:
    """Admin-visible reason for a request row.

    Exhausted retries are stored as ``provider_failed`` (what the client is
    told). The log should show why the *last* attempt died: ``arbiter_rejected``
    vs a transport/protocol ``provider_error``, not a blanket provider failure.
    """
    outcome = getattr(req, "outcome", None) or ""
    if outcome != "provider_failed":
        return outcome
    attempts = list(getattr(req, "attempts", None) or [])
    if not attempts:
        return "provider_failed"
    last = max(attempts, key=lambda a: getattr(a, "attempt_number", 0))
    cls = getattr(last, "error_class", None)
    if cls == "arbiter_rejected":
        return "arbiter_rejected"
    if cls in _TRANSPORT_ERROR_CLASSES:
        return "provider_error"
    if cls:
        return cls
    return "provider_failed"


def state_badge(state: str | None) -> Markup:
    label = state_label(state)
    return Markup(
        f'<span class="badge text-bg-{escape(state_tag(state or ""))}">{escape(label)}</span>'
    )


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def fmt_when(dt: datetime) -> str:
    """Relative for recent rows; otherwise date + time without microseconds."""
    now = datetime.now(UTC)
    d = _aware(dt)
    secs = int((now - d).total_seconds())
    if 0 <= secs < 45:
        return "just now"
    if 45 <= secs < 90:
        return "1m ago"
    if 90 <= secs < 3600:
        return f"{secs // 60}m ago"
    if 3600 <= secs < 86400:
        return f"{secs // 3600}h ago"
    if 86400 <= secs < 86400 * 2:
        return "1d ago"
    if 86400 * 2 <= secs < 86400 * 7:
        return f"{secs // 86400}d ago"
    return d.strftime("%Y-%m-%d %H:%M")


def fmt_when_title(dt: datetime) -> str:
    return _aware(dt).strftime("%Y-%m-%d %H:%M:%S UTC")


def when(dt: datetime | None) -> Markup:
    if dt is None:
        return Markup("—")
    return Markup(
        f'<time datetime="{escape(dt.isoformat())}" title="{escape(fmt_when_title(dt))}">{escape(fmt_when(dt))}</time>'
    )


def pager_summary(total: int, page: int, per_page: int) -> str:
    if total <= per_page:
        return f"{total} total"
    return f"{total} total — page {page} ({per_page}/page)"


_AUDIT_EVENT_LABELS = {
    "action.created": "Created action",
    "action.version_submitted": "Submitted version",
    "version.approved": "Approved version",
    "version.rejected": "Rejected version",
    "action.withdrawn": "Withdrew action",
    "enrollment.requested": "Requested enrollment",
    "enrollment.approved": "Approved enrollment",
    "enrollment.rejected": "Rejected enrollment",
    "enrollment.revoked": "Revoked enrollment",
    "enrollment.reset": "Reset enrollment",
    "enrollment.admin_granted": "Admin enrolled client",
    "agent.registered": "Registered agent",
    "agent.edited": "Edited agent",
    "agent.key_revoked": "Revoked key",
    "agent.key_issued": "Issued key",
    "request.invoked": "Invoked action",
}


def audit_event_label(event: str | None) -> str:
    if not event:
        return ""
    if event in _AUDIT_EVENT_LABELS:
        return _AUDIT_EVENT_LABELS[event]
    return state_label(event.replace(".", "_"))


def audit_detail_summary(detail: dict | None) -> str:
    """One-line operator summary; omit empty/null notes and null fields."""
    if not detail:
        return ""
    parts: list[str] = []
    notes = detail.get("notes")
    if isinstance(notes, str) and notes.strip():
        parts.append(notes.strip())
    version_number = detail.get("version_number")
    if version_number is not None and version_number != "":
        parts.append(f"v{version_number}")
    name = detail.get("name")
    if isinstance(name, str) and name.strip():
        parts.append(name.strip())
    code = detail.get("code")
    if code:
        parts.append(str(code))
    status = detail.get("status")
    if status is not None and status != "" and code is None:
        parts.append(f"status {status}")
    skip = {"notes", "action_id", "agent_id", "version_number", "name", "code", "status"}
    for key, value in detail.items():
        if key in skip or value is None or value == "" or value == {}:
            continue
        if isinstance(value, bool):
            parts.append(key if value else f"not {key}")
            continue
        parts.append(f"{key} {value}")
    return " · ".join(parts)


def dispatch_target(framing: dict | None) -> str:
    """Protocol plus URL (post/completions) or command (exec) for the request log.

    Protocol with no target is "—" (not ``exec —`` / ``post —``).
    """
    if not framing:
        return "—"
    protocol = str(framing.get("protocol") or "")
    if protocol in ("post", "completions"):
        endpoint = str(framing.get("endpoint") or "").strip()
        if not endpoint:
            return "—"
        return f"{protocol} {endpoint}"
    if protocol == "exec":
        command = str(framing.get("command") or "").strip()
        if not command:
            return "—"
        return f"{protocol} {command}"
    return protocol or "—"


def request_dispatch_target(req: Any) -> str:
    attempts = getattr(req, "attempts", None) or []
    if not attempts:
        return "—"
    return dispatch_target(attempts[0].framing)


def request_agent_name(req: Any) -> str:
    agent = getattr(req, "agent", None)
    if agent is not None and getattr(agent, "name", None):
        return str(agent.name)
    agent_id = getattr(req, "agent_id", None)
    return str(agent_id) if agent_id else "—"


def delivery_summary(cfg: dict | None) -> str:
    """Protocol plus command (exec) or endpoint (post/completions) for the agent list."""
    if not cfg:
        return "—"
    protocol = str(cfg.get("protocol") or "")
    if protocol == "exec":
        return f"{protocol} {cfg.get('command') or '—'}"
    if protocol in ("post", "completions"):
        return f"{protocol} {cfg.get('endpoint') or '—'}"
    return protocol or "—"


bp.add_app_template_global(state_tag)
bp.add_app_template_global(state_label)
bp.add_app_template_global(state_badge)
bp.add_app_template_global(log_outcome)
bp.add_app_template_global(when)
bp.add_app_template_global(pager_summary)
bp.add_app_template_global(dispatch_target)
bp.add_app_template_global(request_dispatch_target)
bp.add_app_template_global(request_agent_name)
bp.add_app_template_global(delivery_summary)
bp.add_app_template_global(audit_event_label)
bp.add_app_template_global(audit_detail_summary)


# --- T4.3: auth guard (#17/#23) -----------------------------------------------


def _admin_from_bearer() -> str | None:
    """Bearer header is validated first and exclusively when present."""
    token = bearer_token()
    if token is None:
        return None
    with _session_scope() as db:
        identity = resolve_bearer(db, current_app.config["DMZ"], token)
    if identity is not None and identity.kind == "admin":
        return identity.admin.username if identity.admin else "admin"
    return None


def _session_scope():
    from admz.core.db import session_scope

    return session_scope(current_app)


def current_admin() -> str | None:
    return _admin_from_bearer() or session.get("admin")


def admin_required(
    *, page: bool = False, csrf: bool = True
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Guard: bearer admin token first, else session (#23).

    ``page`` routes redirect anonymous users to login; fragment and mutating
    routes return 401 JSON. Form POSTs require the per-session CSRF token;
    bearer-token mutations are exempt (the header is the CSRF defense).
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            token = bearer_token()
            if token is not None:
                from admz.core.keys import CHECKSUM_MESSAGE, KeyChecksumError, assert_key_checksum

                try:
                    assert_key_checksum(token)
                except KeyChecksumError:
                    if page:
                        return redirect(url_for("admin.login"))
                    return (
                        jsonify(
                            {
                                "error": {
                                    "code": "key_checksum_invalid",
                                    "message": CHECKSUM_MESSAGE,
                                }
                            }
                        ),
                        401,
                    )
            admin = current_admin()
            if admin is None:
                if page:
                    return redirect(url_for("admin.login"))
                return jsonify({"error": {"code": "unauthorized", "message": "Admin auth required."}}), 401
            if csrf and request.method == "POST" and not bearer_token():
                token = request.form.get("csrf_token", "")
                if not token or not secrets.compare_digest(token, session.get("csrf_token", "")):
                    return (
                        jsonify({"error": {"code": "forbidden", "message": "CSRF token mismatch."}}),
                        400,
                    )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def csrf_token() -> str:
    """Per-session CSRF token; generated lazily on first use (#23)."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(24)
    return session["csrf_token"]


# --- T4.6: multi-patch SSE merge responses (#25) -------------------------------


def sse_merge(
    patches: list[tuple[str, str]],
    remove_signals: list[str] | None = None,
    signals: dict[str, Any] | None = None,
) -> Response:
    """Datastar SSE merge response: one event per (selector, html) patch.

    Event formatting is delegated to the official ``datastar-py`` SDK
    (datastar_py.ServerSentEventGenerator, version-matched to the vendored
    datastar 1.0.2 bundle; the core generator is framework-agnostic so it
    works with Flask). We use ``mode inner`` because the partial HTML is
    content for the target element, not a replacement carrying the target's
    own id.

    ``remove_signals`` optionally precedes the patches with a
    ``datastar-patch-signals`` event nulling those signal names (Datastar's
    mergePatch deletes a signal when a patch sets it to null). Needed when a
    patched form re-declares ``data-signals``: signals are a global store and
    are NOT removed when their element is replaced, so values from a previous
    agent's form would otherwise leak into the new one.
    """
    body = ""
    if remove_signals:
        body += SSE.patch_signals({name: None for name in remove_signals})
    body += "".join(
        SSE.patch_elements(html, selector=selector, mode=ElementPatchMode.INNER)
        for selector, html in patches
    )
    if signals:
        body += SSE.patch_signals(signals)
    response = Response(body, content_type="text/event-stream; charset=utf-8")
    response.headers["Cache-Control"] = "no-cache"
    return response


# --- Login --------------------------------------------------------------------


@bp.get("/login")
def login():
    if current_admin():
        return redirect(url_for("admin.dashboard"))
    return render_template("login.html", csrf_token=csrf_token(), username="")

@bp.post("/login")
def login_post():
    from admz.core.config import AdminAccount

    config = current_app.config["DMZ"]
    if request.is_json:
        username = (request.get_json(silent=True) or {}).get("username", "")
        password = request.json.get("password", "")
    else:
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if not secrets.compare_digest(request.form.get("csrf_token", ""), csrf_token()):
            return render_template(
                "login.html",
                error="CSRF token mismatch.",
                csrf_token=csrf_token(),
                username=username,
            ), 400
    for admin in config.admins:
        assert isinstance(admin, AdminAccount)
        if admin.username == username and admin.check_password(password):
            session.clear()
            session["admin"] = username
            session.permanent = True
            csrf_token()  # establish the per-session token
            if request.is_json:
                return jsonify({"ok": True})
            return redirect(url_for("admin.dashboard"))
    if request.is_json:
        return jsonify({"error": {"code": "unauthorized", "message": "Bad credentials."}}), 401
    return render_template(
        "login.html",
        error="Invalid username or password.",
        csrf_token=csrf_token(),
        username=username,
    ), 401


@bp.post("/logout")
def logout():
    session.clear()
    if request.is_json or bearer_token():
        return jsonify({"ok": True})
    return redirect(url_for("admin.login"))


# --- Shared helpers for the console routes ------------------------------------


def _db():
    """Session scope bound to the current app."""
    from admz.core.db import session_scope

    return session_scope(current_app)


def _render_partial(
    template: str,
    target: str | None = None,
    remove_signals: list[str] | None = None,
    signals: dict[str, Any] | None = None,
    **ctx,
):
    """Render a partial; when a CSS selector is given, wrap as a Datastar SSE
    merge response so the browser patches it into that target element.

    Datastar actions require `text/event-stream` responses carrying
    `datastar-merge-fragments` events - a bare text/html body is fetched but
    never merged.
    """
    html = render_template(template, csrf_token=csrf_token(), **ctx)
    if target is not None:
        return sse_merge(
            [(target, html)], remove_signals=remove_signals, signals=signals
        )
    return html


def _actor() -> str:
    return current_admin() or "admin"


def _audit(session, event: str, target_type: str, target_id: str, detail=None) -> None:
    from admz.core.audit import audit

    audit(
        session,
        actor_type="admin",
        actor_id=_actor(),
        event=event,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
