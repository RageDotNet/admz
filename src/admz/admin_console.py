"""Admin console page/fragment/mutation routes (webui-v2.md route table, #27)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode

from flask import abort, current_app, render_template, request
from markupsafe import escape
from sqlalchemy.exc import IntegrityError

from admz.core import storage
from admz.core.jsondiff import compact_payload_diff

from .admin import (
    _actor,
    _audit,
    _db,
    _render_partial,
    admin_required,
    audit_detail_summary,
    audit_event_label,
    bp,
    csrf_token,
    sse_merge,
    state_badge,
    state_label,
)

__all__ = []


def _public_origin() -> str:
    """Origin the administrator used (or DMZ_PUBLIC_BASE_URL / public_base_url)."""
    override = (current_app.config["DMZ"].public_base_url or "").strip().rstrip("/")
    if override:
        return override
    return request.url_root.rstrip("/")


def _agent_onboarding_prompt(
    *, key: str, is_client: bool, is_provider: bool, origin: str
) -> str:
    """Plaintext for the admin to paste into a client/provider agent."""
    lines = [
        "You have access to Agent DMZ, a broker between you and trusted providers. "
        "Do not call providers directly.",
        "",
        f"Base URL: {origin}",
        f"Bearer key: {key}",
        f"Use this header on every request: Authorization: Bearer {key}",
        "",
    ]
    if is_client and is_provider:
        lines.extend(
            [
                "You may act as both a client and a provider. Read both skills:",
                f"{origin}/v2/skill/client",
                f"{origin}/v2/skill/provider",
                "",
                "Fetch those URLs (no auth required), follow the skills, and use only "
                "the /v2 API at that base URL.",
            ]
        )
    elif is_client:
        lines.extend(
            [
                "Read your operating instructions from:",
                f"{origin}/v2/skill/client",
                "",
                "Fetch that URL (no auth required), follow the skill, and use only "
                "the /v2 API at that base URL.",
            ]
        )
    else:
        lines.extend(
            [
                "You publish and serve actions; clients never talk to you except "
                "through the DMZ.",
                "Read your operating instructions from:",
                f"{origin}/v2/skill/provider",
                "",
                "Fetch that URL (no auth required), follow the skill, and use only "
                "the /v2 API at that base URL.",
            ]
        )
    return "\n".join(lines)


def _data() -> dict:
    """Request payload dict from form or JSON body (empty when neither)."""
    if request.mimetype in ('application/x-www-form-urlencoded', 'multipart/form-data'):
        return dict(request.form)
    if request.is_json:
        return request.get_json(silent=True) or {}
    return {}


def _paged(default_per: int = 50, cap: int = 100):
    page, per_page = storage.clamp_page(
        request.args.get("page"), request.args.get("per_page"),
        max_per_page=cap, default_per_page=default_per,
    )
    return page, per_page


_DIRECTORY_STATES = frozenset({"pending", "active", "withdrawn"})
_DIRECTORY_DEFAULT_PER = 50
_ENROLL_DECIDED = frozenset({"enrolled", "rejected", "revoked"})
_ENROLL_DEFAULT_PER = 20
_AGENTS_DEFAULT_PER = 50
_LOG_DEFAULT_PER = 50
_IN_FLIGHT_OUTCOMES = (
    "received",
    "arbiter_reviewing_request",
    "dispatching",
    "arbiter_reviewing_response",
)
_REQUEST_DETAIL_TARGETS = {
    "log": "#request-detail",
    "action": "#action-request-detail",
}
_AUDIT_DEFAULT_PER = 50
_AUDIT_TRAFFIC_EVENTS = ("request.invoked", "request.invoked")
_AUDIT_KINDS = frozenset({"lifecycle", "traffic", "all"})


def _directory_partial_url(*, page: int, q: str, state: str, per_page: int) -> str:
    params: dict[str, str | int] = {"page": page}
    if q:
        params["q"] = q
    if state:
        params["state"] = state
    if per_page != _DIRECTORY_DEFAULT_PER:
        params["per_page"] = per_page
    return "/admin/partials/directory?" + urlencode(params)


# --- T4.8/T4.9: dashboard shell + stats ----------------------------------------


@bp.get("")
@admin_required(page=True, csrf=False)
def dashboard():
    from .admin import current_admin

    return render_template(
        "dashboard.html",
        admin=current_admin(),
    )


@bp.get("/partials/stats")
@admin_required(page=False, csrf=False)
def partial_stats():
    return sse_merge([("#stats-bar", _stats_html())])


# --- T4.10: directory tab -------------------------------------------------------


@bp.get("/partials/directory")
@admin_required(page=False, csrf=False)
def partial_directory():
    page, per_page = _paged(default_per=_DIRECTORY_DEFAULT_PER)
    q = (request.args.get("q") or "").strip() or None
    state = (request.args.get("state") or "").strip() or None
    if state not in _DIRECTORY_STATES:
        state = None
    with _db() as session:
        actions, total = storage.list_actions(
            session, page=page, per_page=per_page, q=q, state=state
        )
        rows = []
        for a in actions:
            # Force-load the lazy `versions` relationship while the session is
            # open: the template accesses `action.active_version` after the
            # session closes (DetachedInstanceError otherwise).
            a.versions  # noqa: B018
            _, enroll_total = storage.list_enrollments(
                session, action_id=a.id, state="enrolled", page=1, per_page=1
            )
            rows.append(
                {
                    "action": a,
                    "owner": storage.get_agent(session, a.owner_agent_id),
                    "pending_version": storage.submitted_version(session, a.id),
                    "enrolled_count": enroll_total,
                }
            )
    q_s = q or ""
    state_s = state or ""
    return _render_partial(
        "partials/directory.html",
        target="#directory-list",
        rows=rows,
        page=page,
        per_page=per_page,
        total=total,
        q=q_s,
        state=state_s,
        pager_prev=_directory_partial_url(
            page=page - 1, q=q_s, state=state_s, per_page=per_page
        ),
        pager_next=_directory_partial_url(
            page=page + 1, q=q_s, state=state_s, per_page=per_page
        ),
        filters_active=bool(q_s or state_s),
    )


# --- T4.13: per-action detail ---------------------------------------------------


@bp.get("/partials/action/<action_id>")
@admin_required(page=False, csrf=False)
def partial_action(action_id: str):
    with _db() as session:
        action = storage.get_action(session, action_id)
        if action is None:
            abort(404)
        versions = storage.list_versions(session, action_id)
        active = action.active_version
        diffs: dict[int, dict] = {}
        prev = None
        for v in versions:
            if prev is None:
                diffs[v.version_number] = {}
            else:
                diffs[v.version_number] = compact_payload_diff(prev.payload, v.payload)
            prev = v
        enrollments, _ = storage.list_enrollments(
            session, action_id=action_id, page=1, per_page=100
        )
        requests, _ = storage.list_requests(
            session, action_id=action_id, page=1, per_page=20
        )
        owner = storage.get_agent(session, action.owner_agent_id)
        agent_names = {}
        enrolled_ids = set()
        for e in enrollments:
            enrolled_ids.add(e.agent_id)
            owner_agent = storage.get_agent(session, e.agent_id)
            agent_names[e.agent_id] = owner_agent.name if owner_agent else e.agent_id
        agents, _ = storage.list_agents(session, page=1, per_page=500)
        enrollable = [
            a for a in agents if a.is_client and a.id not in enrolled_ids and not a.disabled
        ]
    return _render_partial(
        "partials/action_detail.html",
        target="#action-detail",
        action=action,
        versions=versions,
        active=active,
        diffs=diffs,
        enrollments=enrollments,
        agent_names=agent_names,
        enrollable=enrollable,
        requests=requests,
        owner=owner,
    )


# --- T4.14: version approve/reject (multi-patch SSE, #25) ----------------------


def _queue_patches(extra: list[tuple[str, str]]) -> Any:

    patches = list(extra)
    patches.append(("#stats-bar", _stats_html()))
    patches.append(("#enrollments-panel", _enrollments_panel_html()))
    return patches


def _stats_html() -> str:
    with _db() as session:
        agents, agent_total = storage.list_agents(session, page=1, per_page=1)
        by_state = {"pending": 0, "active": 0, "withdrawn": 0}
        actions, _ = storage.list_actions(session, page=1, per_page=500)
        for a in actions:
            by_state[a.state] = by_state.get(a.state, 0) + 1
        _, pending_enrollments = storage.list_enrollments(
            session, state="requested", page=1, per_page=1
        )
        outcome_counts = dict(storage.outcome_counts(session))
        last_24h = storage.requests_last_24h(session)
    return _render_partial(
        "partials/stats.html",
        agent_count=agent_total,
        actions_by_state=by_state,
        pending_enrollments=pending_enrollments,
        outcome_counts=outcome_counts,
        last_24h=last_24h,
    )


def _enrollments_partial_url(
    *, page: int, action_id: str, client: str, state: str, per_page: int
) -> str:
    params: dict[str, str | int] = {"page": page}
    if action_id:
        params["action_id"] = action_id
    if client:
        params["client"] = client
    if state:
        params["state"] = state
    if per_page != _ENROLL_DEFAULT_PER:
        params["per_page"] = per_page
    return "/admin/partials/enrollments?" + urlencode(params)


def _enrollments_panel_html() -> str:
    page, per_page = _paged(default_per=_ENROLL_DEFAULT_PER)
    action_q = (request.args.get("action_id") or "").strip() or None
    client_q = (request.args.get("client") or "").strip() or None
    state = (request.args.get("state") or "").strip() or None
    if state not in _ENROLL_DECIDED:
        state = None
    decided_states = [state] if state else list(_ENROLL_DECIDED)
    with _db() as session:
        pending, _ = storage.list_enrollments(
            session, state="requested", page=1, per_page=100
        )
        pending_rows = [
            {"enrollment": e, "agent": storage.get_agent(session, e.agent_id)}
            for e in pending
        ]
        decided, total = storage.list_enrollments(
            session,
            states=decided_states,
            action_q=action_q,
            client_q=client_q,
            order="decided",
            page=page,
            per_page=per_page,
        )
        decided_rows = [
            {"enrollment": e, "agent": storage.get_agent(session, e.agent_id)}
            for e in decided
        ]
    filters_active = bool(action_q or client_q or state)
    return _render_partial(
        "partials/enrollments.html",
        pending_rows=pending_rows,
        decided_rows=decided_rows,
        total=total,
        page=page,
        per_page=per_page,
        action_id=action_q or "",
        client=client_q or "",
        state=state or "",
        filters_active=filters_active,
        pager_prev=_enrollments_partial_url(
            page=page - 1,
            action_id=action_q or "",
            client=client_q or "",
            state=state or "",
            per_page=per_page,
        ),
        pager_next=_enrollments_partial_url(
            page=page + 1,
            action_id=action_q or "",
            client=client_q or "",
            state=state or "",
            per_page=per_page,
        ),
    )


@bp.post("/action-version/<version_id>/approve")
@admin_required(page=False)
def approve_version(version_id: str):
    notes = _data().get("notes")
    with _db() as session:
        from admz.core.models import ActionVersion

        version = session.get(ActionVersion, version_id)
        if version is None or version.state != "submitted":
            abort(404)
        action = storage.decide_version(
            session, version, decision="approved", decided_by=_actor(), notes=notes
        )
        _audit(
            session, "version.approved", "action_version", version_id,
            {"action_id": action.id, "notes": notes},
        )
        version_id_str = str(version.id)
    return sse_merge(
        _queue_patches([
            (f"#version-{version_id_str}-state", str(state_badge("active"))),
            (f"#action-{action.id}-state", str(state_badge("active"))),
            (f"#dir-action-{action.id}-state", str(state_badge("active"))),
        ])
    )


@bp.post("/action-version/<version_id>/reject")
@admin_required(page=False)
def reject_version(version_id: str):
    notes = _data().get("notes")
    with _db() as session:
        from admz.core.models import ActionVersion

        version = session.get(ActionVersion, version_id)
        if version is None or version.state != "submitted":
            abort(404)
        action = storage.decide_version(
            session, version, decision="rejected", decided_by=_actor(), notes=notes
        )
        _audit(
            session, "version.rejected", "action_version", version_id,
            {"action_id": action.id, "notes": notes},
        )
        version_id_str = str(version.id)
    return sse_merge(
        _queue_patches([
            (f"#version-{version_id_str}-state", str(state_badge("rejected"))),
        ])
    )


@bp.post("/action/<action_id>/withdraw")
@admin_required(page=False)
def admin_withdraw(action_id: str):
    with _db() as session:
        action = storage.get_action(session, action_id)
        if action is None:
            abort(404)
        action.state = "withdrawn"
        _audit(session, "action.withdrawn", "action", action_id, {"by": "admin"})
    return sse_merge(
        _queue_patches([
            (f"#action-{action_id}-state", str(state_badge("withdrawn"))),
            (f"#dir-action-{action_id}-state", str(state_badge("withdrawn"))),
        ])
    )


# --- T4.15: enrollment queue + decisions ---------------------------------------


@bp.get("/partials/enrollments")
@admin_required(page=False, csrf=False)
def partial_enrollments():
    return sse_merge([("#enrollments-panel", _enrollments_panel_html())])


def _enrollment_or_404(session, enrollment_id):
    from admz.core.models import Enrollment

    e = session.get(Enrollment, enrollment_id)
    if e is None:
        abort(404)
    return e


def _enrollment_patches() -> list[tuple[str, str]]:
    return _queue_patches([])


@bp.post("/enrollment/<enrollment_id>/approve")
@admin_required(page=False)
def approve_enrollment(enrollment_id: str):
    notes = _data().get("notes")
    with _db() as session:
        e = _enrollment_or_404(session, enrollment_id)
        storage.decide_enrollment(
            session, e, decision="approved", decided_by=_actor(), notes=notes
        )
        _audit(session, "enrollment.approved", "enrollment", enrollment_id, {"notes": notes})
        action_id = e.action_id
    return sse_merge(_enrollment_patches() + [("#action-access", _action_access_html(action_id))])


@bp.post("/enrollment/<enrollment_id>/reject")
@admin_required(page=False)
def reject_enrollment(enrollment_id: str):
    notes = _data().get("notes")
    with _db() as session:
        e = _enrollment_or_404(session, enrollment_id)
        storage.decide_enrollment(
            session, e, decision="rejected", decided_by=_actor(), notes=notes
        )
        _audit(session, "enrollment.rejected", "enrollment", enrollment_id, {"notes": notes})
        action_id = e.action_id
    return sse_merge(_enrollment_patches() + [("#action-access", _action_access_html(action_id))])


@bp.post("/enrollment/<enrollment_id>/revoke")
@admin_required(page=False)
def revoke_enrollment(enrollment_id: str):
    with _db() as session:
        e = _enrollment_or_404(session, enrollment_id)
        storage.decide_enrollment(session, e, decision="revoked", decided_by=_actor())
        _audit(session, "enrollment.revoked", "enrollment", enrollment_id)
        action_id = e.action_id
    return sse_merge(_enrollment_patches() + [("#action-access", _action_access_html(action_id))])


@bp.post("/enrollment/<enrollment_id>/reset")
@admin_required(page=False)
def reset_enrollment(enrollment_id: str):
    """Reset a rejected enrollment so the client may re-request (#11)."""
    with _db() as session:
        e = _enrollment_or_404(session, enrollment_id)
        if e.state != "rejected":
            abort(400)
        storage.decide_enrollment(session, e, decision="reset", decided_by=_actor())
        _audit(session, "enrollment.reset", "enrollment", enrollment_id)
    return sse_merge(_enrollment_patches())


def _action_access_html(action_id: str) -> str:
    with _db() as session:
        action = storage.get_action(session, action_id)
        if action is None:
            abort(404)
        enrollments, _ = storage.list_enrollments(
            session, action_id=action_id, page=1, per_page=100
        )
        agent_names = {}
        enrolled_ids = set()
        for e in enrollments:
            enrolled_ids.add(e.agent_id)
            owner_agent = storage.get_agent(session, e.agent_id)
            agent_names[e.agent_id] = owner_agent.name if owner_agent else e.agent_id
        agents, _ = storage.list_agents(session, page=1, per_page=500)
        enrollable = [
            a for a in agents if a.is_client and a.id not in enrolled_ids and not a.disabled
        ]
    return render_template(
        "partials/action_access.html",
        csrf_token=csrf_token(),
        action=action,
        enrollments=enrollments,
        agent_names=agent_names,
        enrollable=enrollable,
    )


@bp.post("/action/<action_id>/enroll")
@admin_required(page=False)
def admin_enroll(action_id: str):
    """Admin-initiated enrollment (client + action)."""
    agent_id = _data().get("agent_id")
    with _db() as session:
        from admz.core.models import Enrollment

        if storage.get_action(session, action_id) is None or not agent_id:
            abort(404)
        existing = storage.find_enrollment(session, agent_id=agent_id, action_id=action_id)
        if existing is not None:
            abort(409)
        e = Enrollment(agent_id=agent_id, action_id=action_id, state="enrolled")
        session.add(e)
        session.flush()
        _audit(session, "enrollment.admin_granted", "enrollment", str(e.id),
               {"action_id": action_id, "agent_id": agent_id})
    return sse_merge(_enrollment_patches() + [("#action-access", _action_access_html(action_id))])


# --- T4.17: agents tab ----------------------------------------------------------

_DELIVERY_PROTOCOLS = ("post", "exec", "completions")
_HEADER_ROWS = 5  # matches the 5 client-side header rows in delivery_fields.html

# Every `edit_*` signal delivery_fields.html can declare (sig='edit'). Nulled
# then replaced when the agent-detail form is patched so a previous agent's
# values don't leak into the next one (signals are a global browser-side store).
_EDIT_SIGNALS = ["edit_provider", "edit_protocol", "edit_headerRows"] + [
    f"edit_{k}{i}" for i in range(_HEADER_ROWS) for k in ("hk", "hv")
]


def _delivery_edit_signals(agent: Any) -> dict[str, Any]:
    """Authoritative Datastar signals for the edit-agent delivery form."""
    cfg = agent.delivery_config or {}
    headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else {}
    pairs = [(str(k), str(v)) for k, v in headers.items()]
    signals: dict[str, Any] = {
        "edit_provider": bool(agent.is_provider),
        "edit_protocol": (cfg.get("protocol") or "post"),
        "edit_headerRows": max(1, len(pairs)),
    }
    for i in range(_HEADER_ROWS):
        if i < len(pairs):
            signals[f"edit_hk{i}"], signals[f"edit_hv{i}"] = pairs[i]
        else:
            signals[f"edit_hk{i}"] = ""
            signals[f"edit_hv{i}"] = ""
    return signals


def _compose_delivery(data: dict[str, str]) -> dict[str, Any]:
    """Structured form fields -> delivery_config dict (write-only, #16).

    Only fields relevant to the chosen protocol are stored; empty optional
    values are omitted; duplicate header names last-win; unknown protocol or
    non-numeric retries/timeout is a client error.
    """
    protocol = (data.get("protocol") or "post").strip()
    if protocol not in _DELIVERY_PROTOCOLS:
        abort(400)
    cfg: dict[str, Any] = {"protocol": protocol}
    if protocol in ("post", "completions"):
        endpoint = (data.get("endpoint") or "").strip()
        headers: dict[str, str] = {}
        raw_rows = (data.get("header_rows") or "").strip()
        if raw_rows:
            if not raw_rows.isdigit():
                abort(400)
            used_rows = min(_HEADER_ROWS, int(raw_rows))
        else:
            used_rows = _HEADER_ROWS
        for i in range(used_rows):
            key = (data.get(f"header_key_{i}") or "").strip()
            value = (data.get(f"header_value_{i}") or "").strip()
            if key:
                headers[key] = value
        if endpoint:
            cfg["endpoint"] = endpoint
        if headers:
            cfg["headers"] = headers
        if protocol == "completions":
            model = (data.get("model") or "").strip()
            if model:
                cfg["model"] = model
    elif protocol == "exec":
        command = (data.get("command") or "").strip()
        if command:
            cfg["command"] = command
    for knob in ("retries", "timeout"):
        raw = (data.get(knob) or "").strip()
        if raw:
            if not raw.isdigit():
                abort(400)
            cfg[knob] = int(raw)
    return cfg


def _register_error_html(message: str) -> str:
    return (
        f'<div class="alert alert-danger py-2 mb-0" role="alert">{escape(message)}</div>'
    )


def _agents_partial_url(*, page: int, per_page: int) -> str:
    params: dict[str, str | int] = {"page": page}
    if per_page != _AGENTS_DEFAULT_PER:
        params["per_page"] = per_page
    return "/admin/partials/agents?" + urlencode(params)


@bp.get("/partials/agents")
@admin_required(page=False, csrf=False)
def partial_agents():
    page, per_page = _paged(default_per=_AGENTS_DEFAULT_PER)
    with _db() as session:
        agents, total = storage.list_agents(session, page=page, per_page=per_page)
    return _render_partial(
        "partials/agents.html",
        agents=agents,
        page=page,
        per_page=per_page,
        total=total,
        pager_prev=_agents_partial_url(page=page - 1, per_page=per_page),
        pager_next=_agents_partial_url(page=page + 1, per_page=per_page),
        target="#agents-list",
    )


@bp.post("/agents")
@admin_required(page=False)
def register_agent():
    """Register agent; plaintext key returned exactly once (#16)."""
    data = _data()
    name = (data.get("name") or "").strip()
    if not name:
        return sse_merge([("#agent-register-error", _register_error_html("Name is required."))])
    is_client = data.get("is_client") in ("on", "true", True, 1)
    is_provider = data.get("is_provider") in ("on", "true", True, 1)
    if not (is_client or is_provider):
        return sse_merge([
            (
                "#agent-register-error",
                _register_error_html("Pick at least one capability (client or provider)."),
            )
        ])
    try:
        with _db() as session:
            payload_chars = current_app.config["DMZ"].key_payload_chars
            agent, key = storage.register_agent(
                session,
                name=name,
                is_client=is_client,
                is_provider=is_provider,
                key_payload_chars=payload_chars,
            )
            if is_provider:
                agent.delivery_config = _compose_delivery(data)
            agent_id = agent.id
            _audit(session, "agent.registered", "agent", agent_id, {"name": name})
    except IntegrityError:
        return sse_merge([
            (
                "#agent-register-error",
                _register_error_html("An agent with that name already exists."),
            )
        ])
    return sse_merge([
        ("#agent-register-error", ""),
        (
            "#agent-key-reveal",
            _render_partial(
                "partials/key_reveal.html",
                key=key,
                agent_id=agent_id,
                prompt=_agent_onboarding_prompt(
                    key=key,
                    is_client=is_client,
                    is_provider=is_provider,
                    origin=_public_origin(),
                ),
            ),
        ),
    ])


@bp.get("/agents/<agent_id>")
@admin_required(page=False, csrf=False)
def agent_detail(agent_id: str):
    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        if agent is None:
            abort(404)
    return _render_partial(
        "partials/agent_detail.html",
        agent=agent,
        target="#agent-detail-region",
        remove_signals=_EDIT_SIGNALS,
        signals=_delivery_edit_signals(agent),
    )


@bp.post("/agents/<agent_id>")
@admin_required(page=False)
def agent_edit(agent_id: str):
    data = _data()
    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        if agent is None:
            abort(404)
        agent.is_client = data.get("is_client") in ("on", "true", True, 1)
        agent.is_provider = data.get("is_provider") in ("on", "true", True, 1)
        agent.disabled = data.get("enabled") not in ("on", "true", True, 1)
        # Structured delivery fields; clearing the provider flag clears config.
        agent.delivery_config = _compose_delivery(data) if agent.is_provider else None
        _audit(session, "agent.edited", "agent", agent_id)
    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        assert agent is not None
    # Patch the wrapper region (mode inner), not the detail card itself: the
    # partial's root carries the card's own id, and morphing an element that
    # contains the patch target into that target throws HierarchyRequestError.
    return _render_partial(
        "partials/agent_detail.html",
        agent=agent,
        saved=True,
        target="#agent-detail-region",
        remove_signals=_EDIT_SIGNALS,
        signals=_delivery_edit_signals(agent),
    )


def _connection_test_html(result) -> str:
    return render_template("partials/connection_test.html", result=result)


@bp.post("/agents/<agent_id>/test-delivery")
@admin_required(page=False)
def agent_test_delivery(agent_id: str):
    """Probe saved provider delivery settings (not unsaved form edits)."""
    from admz.dispatch.adapters import (
        ConnectionTestResult,
        _default_poster,
        _default_runner,
        ping_provider,
    )

    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        if agent is None:
            abort(404)
        is_provider = agent.is_provider
        delivery = dict(agent.delivery_config or {})
    if not is_provider:
        result = ConnectionTestResult(ok=False, summary="This agent is not a provider.")
    elif not delivery:
        result = ConnectionTestResult(
            ok=False,
            summary="No saved delivery settings. Save the form first, then test.",
        )
    else:
        config = current_app.config["DMZ"]
        poster = current_app.extensions.get("DMZ_POSTER") or _default_poster
        runner = current_app.extensions.get("DMZ_RUNNER") or _default_runner
        result = ping_provider(
            delivery,
            default_timeout=config.dispatch_timeout,
            poster=poster,
            runner=runner,
        )
    return sse_merge([("#agent-delivery-test", _connection_test_html(result))])


@bp.post("/agents/<agent_id>/revoke-key")
@admin_required(page=False)
def agent_revoke_key(agent_id: str):
    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        if agent is None:
            abort(404)
        import secrets as _secrets

        from admz.core.keys import hash_key
        agent.api_key_hash = hash_key("revoked:" + _secrets.token_urlsafe(32))
        _audit(session, "agent.key_revoked", "agent", agent_id)
    return sse_merge([(f"#agent-{agent_id}-key-state", str(state_badge("revoked")))])


@bp.post("/agents/<agent_id>/new-key")
@admin_required(page=False)
def agent_new_key(agent_id: str):
    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        if agent is None:
            abort(404)
        is_client = agent.is_client
        is_provider = agent.is_provider
        key = storage.issue_key(session, agent, key_payload_chars=current_app.config["DMZ"].key_payload_chars)
        _audit(session, "agent.key_issued", "agent", agent_id)
    return sse_merge([
        (
            "#agent-key-reveal",
            _render_partial(
                "partials/key_reveal.html",
                key=key,
                agent_id=agent_id,
                prompt=_agent_onboarding_prompt(
                    key=key,
                    is_client=is_client,
                    is_provider=is_provider,
                    origin=_public_origin(),
                ),
            ),
        ),
        (f"#agent-{agent_id}-key-state", str(state_badge("set"))),
    ])


# --- T4.19: request log ---------------------------------------------------------


def _log_partial_url(*, page: int, action_id: str, outcome: str, per_page: int) -> str:
    params: dict[str, str | int] = {"page": page}
    if action_id:
        params["action_id"] = action_id
    if outcome:
        params["outcome"] = outcome
    if per_page != _LOG_DEFAULT_PER:
        params["per_page"] = per_page
    return "/admin/partials/log?" + urlencode(params)


@bp.get("/partials/log")
@admin_required(page=False, csrf=False)
def partial_log():
    page, per_page = _paged(default_per=_LOG_DEFAULT_PER)
    filter_outcome = (request.args.get("outcome") or "").strip()
    query_outcome = filter_outcome or None
    outcomes = None
    if filter_outcome == "in_flight":
        # Pseudo-filter: any of the in-flight progress states. Keep
        # filter_outcome so the dropdown stays on in_flight after submit.
        outcomes = list(_IN_FLIGHT_OUTCOMES)
        query_outcome = None
    action_id = (request.args.get("action_id") or "").strip()
    with _db() as session:
        rows, total = storage.list_requests(
            session,
            action_id=action_id or None,
            outcome=query_outcome,
            outcomes=outcomes,
            page=page,
            per_page=per_page,
        )
    return _render_partial(
        "partials/log.html",
        target="#log-list",
        rows=rows,
        page=page,
        per_page=per_page,
        total=total,
        outcome=filter_outcome,
        action_id=action_id,
        filters_active=bool(action_id or filter_outcome),
        pager_prev=_log_partial_url(
            page=page - 1, action_id=action_id, outcome=filter_outcome, per_page=per_page
        ),
        pager_next=_log_partial_url(
            page=page + 1, action_id=action_id, outcome=filter_outcome, per_page=per_page
        ),
    )


@bp.get("/partials/request/<request_id>")
@admin_required(page=False, csrf=False)
def partial_request_detail(request_id: str):
    with _db() as session:
        row = storage.get_request(session, request_id)
        if row is None:
            abort(404)
        attempts = storage.list_attempts(session, request_id)
    # Directory action cards use #action-request-detail; the Request log uses
    # #request-detail. Only these two selectors are accepted (no free-form CSS).
    into = (request.args.get("into") or "log").strip()
    if into not in _REQUEST_DETAIL_TARGETS:
        into = "log"
    target = _REQUEST_DETAIL_TARGETS[into]
    return _render_partial(
        "partials/request_detail.html",
        req=row,
        attempts=attempts,
        into=into,
        target=target,
    )


# --- T4.20: audit trail ---------------------------------------------------------


def _audit_partial_url(*, page: int, actor: str, target_type: str, kind: str, per_page: int) -> str:
    params: dict[str, str | int] = {"page": page, "kind": kind}
    if actor:
        params["actor"] = actor
    if target_type:
        params["target_type"] = target_type
    if per_page != _AUDIT_DEFAULT_PER:
        params["per_page"] = per_page
    return "/admin/partials/audit?" + urlencode(params)


def _audit_view_rows(session, events: list) -> list[SimpleNamespace]:
    from sqlalchemy import select

    from admz.core.models import Action, ActionVersion, Agent, Enrollment

    agent_ids: set[str] = set()
    enrollment_ids: set[str] = set()
    version_ids: set[str] = set()
    action_ids: set[str] = set()
    for event in events:
        if event.actor_type == "agent":
            agent_ids.add(event.actor_id)
        if event.target_type == "agent":
            agent_ids.add(event.target_id)
        elif event.target_type == "action":
            action_ids.add(event.target_id)
        elif event.target_type == "enrollment":
            enrollment_ids.add(event.target_id)
        elif event.target_type in ("action_version", "version"):
            version_ids.add(event.target_id)
        detail = event.detail or {}
        if detail.get("agent_id"):
            agent_ids.add(str(detail["agent_id"]))
        if detail.get("action_id"):
            action_ids.add(str(detail["action_id"]))

    enrollments: dict[str, Enrollment] = {}
    if enrollment_ids:
        enrollments = {
            row.id: row
            for row in session.scalars(select(Enrollment).where(Enrollment.id.in_(enrollment_ids)))
        }
        for enrollment in enrollments.values():
            agent_ids.add(enrollment.agent_id)
            action_ids.add(enrollment.action_id)

    versions: dict[str, ActionVersion] = {}
    if version_ids:
        versions = {
            row.id: row
            for row in session.scalars(select(ActionVersion).where(ActionVersion.id.in_(version_ids)))
        }
        for version in versions.values():
            action_ids.add(version.action_id)

    agents: dict[str, Agent] = {}
    if agent_ids:
        agents = {row.id: row for row in session.scalars(select(Agent).where(Agent.id.in_(agent_ids)))}

    existing_actions: set[str] = set()
    if action_ids:
        existing_actions = set(session.scalars(select(Action.id).where(Action.id.in_(action_ids))))

    rows = []
    for event in events:
        detail = event.detail or {}
        actor_agent_id = event.actor_id if event.actor_type == "agent" and event.actor_id in agents else None
        actor_name = event.actor_id
        if actor_agent_id:
            actor_name = agents[actor_agent_id].name
        elif event.actor_type == "admin":
            actor_name = event.actor_id or "admin"

        action_id = detail.get("action_id") if isinstance(detail.get("action_id"), str) else None
        agent_id = detail.get("agent_id") if isinstance(detail.get("agent_id"), str) else None
        action_label = None
        agent_label = None
        fallback = event.target_id
        if event.target_type == "action":
            action_id = event.target_id
            action_label = event.target_id
        elif event.target_type == "agent":
            agent_id = event.target_id
            agent = agents.get(event.target_id)
            agent_label = agent.name if agent is not None else event.target_id
        elif event.target_type == "enrollment":
            enrolled = enrollments.get(event.target_id)
            if enrolled is not None:
                action_id = enrolled.action_id
                agent_id = enrolled.agent_id
                agent = agents.get(enrolled.agent_id)
                agent_label = agent.name if agent is not None else enrolled.agent_id
                action_label = enrolled.action_id
            else:
                fallback = event.target_id
        elif event.target_type in ("action_version", "version"):
            ver = versions.get(event.target_id)
            if ver is not None:
                action_id = ver.action_id
                action_label = f"{ver.action_id} v{ver.version_number}"
            elif action_id:
                action_label = str(action_id)

        live_action_id = action_id if action_id in existing_actions else None
        live_agent_id = agent_id if agent_id in agents else None
        target_label = " ".join(bit for bit in (agent_label, action_label) if bit) or fallback

        rows.append(
            SimpleNamespace(
                occurred_at=event.occurred_at,
                actor_name=actor_name,
                actor_title=f"{event.actor_type}:{event.actor_id}",
                actor_agent_id=actor_agent_id,
                event=event.event,
                event_label=audit_event_label(event.event),
                target_type_label=state_label(event.target_type),
                target_label=target_label,
                target_title=f"{event.target_type}/{event.target_id}",
                action_id=live_action_id,
                action_label=action_label or (action_id or ""),
                agent_id=live_agent_id,
                agent_label=agent_label or "",
                detail_summary=audit_detail_summary(detail if isinstance(detail, dict) else None),
            )
        )
    return rows


@bp.get("/partials/audit")
@admin_required(page=False, csrf=False)
def partial_audit():
    page, per_page = _paged(default_per=_AUDIT_DEFAULT_PER)
    actor = (request.args.get("actor") or request.args.get("actor_id") or "").strip()
    target_type = (request.args.get("target_type") or "").strip()
    kind = (request.args.get("kind") or "lifecycle").strip()
    if kind not in _AUDIT_KINDS:
        kind = "lifecycle"
    events_filter = None
    exclude_events = None
    if kind == "lifecycle":
        exclude_events = list(_AUDIT_TRAFFIC_EVENTS)
    elif kind == "traffic":
        events_filter = list(_AUDIT_TRAFFIC_EVENTS)
    with _db() as session:
        events, total = storage.list_audit_events(
            session,
            actor_q=actor or None,
            target_type=target_type or None,
            events=events_filter,
            exclude_events=exclude_events,
            page=page,
            per_page=per_page,
        )
        rows = _audit_view_rows(session, events)
    return _render_partial(
        "partials/audit.html",
        target="#audit-list",
        rows=rows,
        page=page,
        per_page=per_page,
        total=total,
        actor=actor,
        target_type=target_type,
        kind=kind,
        filters_active=bool(actor or target_type or kind != "lifecycle"),
        pager_prev=_audit_partial_url(
            page=page - 1, actor=actor, target_type=target_type, kind=kind, per_page=per_page
        ),
        pager_next=_audit_partial_url(
            page=page + 1, actor=actor, target_type=target_type, kind=kind, per_page=per_page
        ),
    )


# --- Tools tab: arbiter connectivity ------------------------------------------


@bp.get("/partials/tools")
@admin_required(page=False, csrf=False)
def partial_tools():
    config = current_app.config["DMZ"]
    return _render_partial(
        "partials/tools.html",
        target="#tools-panel",
        arbiter_model=config.arbiter_model,
        arbiter_timeout=config.arbiter_timeout,
    )


@bp.post("/tools/test-arbiter")
@admin_required(page=False)
def tools_test_arbiter():
    from admz.dispatch.adapters import LiteLLMArbiterClient, _litellm_completer, ping_arbiter

    config = current_app.config["DMZ"]
    completer = current_app.extensions.get("DMZ_COMPLETER") or _litellm_completer
    arbiter = current_app.extensions.get("DMZ_ARBITER")
    if isinstance(arbiter, LiteLLMArbiterClient):
        result = arbiter.ping()
    else:
        result = ping_arbiter(config, completer)
    return sse_merge([("#tools-arbiter-result", _connection_test_html(result))])

