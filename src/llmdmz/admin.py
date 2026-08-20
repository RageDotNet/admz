"""Admin console (webui-v2.md): auth guard, login/CSRF, SSE merge helper.

The console blueprint is mounted under /admin on the single Flask app. All
routes exactly match the authoritative route table in webui-v2.md (#27).
"""

from __future__ import annotations

import functools
import secrets
from collections.abc import Callable
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

from llmdmz.core.auth import bearer_token, resolve_bearer

bp = Blueprint("admin", __name__, url_prefix="/admin", template_folder="../templates")

# 0build kit has no per-state badge classes; map domain states to z-tag variants.
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
    # request outcomes (terminal)
    "completed": "success",
    "request_schema_invalid": "warning",
    "arbiter_rejected": "danger",
    "provider_failed": "danger",
    "arbiter_unavailable": "warning",
    "internal_error": "danger",
    # request outcomes (in-flight progress)
    "received": "info",
    "arbiter_reviewing_request": "info",
    "dispatching": "primary",
    "arbiter_reviewing_response": "info",
}


def state_tag(state: str) -> str:
    return STATE_TAG.get(state, "secondary")


bp.add_app_template_global(state_tag)


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
    from llmdmz.core.db import session_scope

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
                from llmdmz.core.keys import CHECKSUM_MESSAGE, KeyChecksumError, assert_key_checksum

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


def sse_merge(patches: list[tuple[str, str]], remove_signals: list[str] | None = None) -> Response:
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
    response = Response(body, content_type="text/event-stream; charset=utf-8")
    response.headers["Cache-Control"] = "no-cache"
    return response


# --- Login --------------------------------------------------------------------


@bp.get("/login")
def login():
    if current_admin():
        return redirect(url_for("admin.dashboard"))
    return render_template("login.html", csrf_token=csrf_token())

@bp.post("/login")
def login_post():
    from llmdmz.core.config import AdminAccount

    config = current_app.config["DMZ"]
    if request.is_json:
        username = (request.get_json(silent=True) or {}).get("username", "")
        password = request.json.get("password", "")
    else:
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if not secrets.compare_digest(request.form.get("csrf_token", ""), csrf_token()):
            return render_template("login.html", error="CSRF token mismatch."), 400
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
    return render_template("login.html", error="Invalid username or password.", csrf_token=csrf_token()), 401


@bp.post("/logout")
def logout():
    session.clear()
    if request.is_json or bearer_token():
        return jsonify({"ok": True})
    return redirect(url_for("admin.login"))


# --- Shared helpers for the console routes ------------------------------------


def _db():
    """Session scope bound to the current app."""
    from llmdmz.core.db import session_scope

    return session_scope(current_app)


def _render_partial(template: str, target: str | None = None, remove_signals: list[str] | None = None, **ctx):
    """Render a partial; when a CSS selector is given, wrap as a Datastar SSE
    merge response so the browser patches it into that target element.

    Datastar actions require `text/event-stream` responses carrying
    `datastar-merge-fragments` events - a bare text/html body is fetched but
    never merged.
    """
    html = render_template(template, csrf_token=csrf_token(), **ctx)
    if target is not None:
        return sse_merge([(target, html)], remove_signals=remove_signals)
    return html


def _actor() -> str:
    return current_admin() or "admin"


def _audit(session, event: str, target_type: str, target_id: str, detail=None) -> None:
    from llmdmz.core.audit import audit

    audit(
        session,
        actor_type="admin",
        actor_id=_actor(),
        event=event,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
