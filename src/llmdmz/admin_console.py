"""Admin console page/fragment/mutation routes (webui-v2.md route table, #27)."""

from __future__ import annotations

from typing import Any

from flask import abort, render_template, request

from llmdmz.core import storage
from llmdmz.core.jsondiff import diff_payloads

from .admin import _actor, _audit, _db, _render_partial, admin_required, bp, sse_merge

__all__ = []


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


# --- T4.8/T4.9: dashboard shell + stats ----------------------------------------


@bp.get("")
@admin_required(page=True, csrf=False)
def dashboard():
    from .admin import current_admin

    return render_template(
        "dashboard.html",
        admin=current_admin(),
        pending_versions=_pending_versions_html(),  # defined below in this module
    )


@bp.get("/partials/stats")
@admin_required(page=False, csrf=False)
def partial_stats():
    return sse_merge([("#stats-bar", _stats_html())])


# --- T4.10: directory tab -------------------------------------------------------


@bp.get("/partials/directory")
@admin_required(page=False, csrf=False)
def partial_directory():
    page, per_page = _paged()
    q = request.args.get("q") or None
    state = request.args.get("state") or None
    with _db() as session:
        actions, total = storage.list_actions(session, page=page, per_page=per_page, q=q)
        if state:
            actions = [a for a in actions if a.state == state]
        rows = []
        for a in actions:
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
    return _render_partial(
        "partials/directory.html",
        target="#directory-list",
        rows=rows,
        page=page,
        per_page=per_page,
        total=total,
        q=q or "",
        state=state or "",
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
        diffs = {}
        for v in versions:
            if active is not None and v.id != active.id:
                diffs[v.version_number] = diff_payloads(active.payload, v.payload)
        enrollments, _ = storage.list_enrollments(
            session, action_id=action_id, page=1, per_page=100
        )
        requests, _ = storage.list_requests(
            session, action_id=action_id, page=1, per_page=20
        )
        owner = storage.get_agent(session, action.owner_agent_id)
    return _render_partial(
        "partials/action_detail.html",
        target="#action-detail",
        action=action,
        versions=versions,
        active=active,
        diffs=diffs,
        enrollments=enrollments,
        requests=requests,
        owner=owner,
    )


# --- T4.14: version approve/reject (multi-patch SSE, #25) ----------------------


def _queue_patches(extra: list[tuple[str, str]]) -> Any:

    patches = list(extra)
    patches.append(("#stats-bar", _stats_html()))
    patches.append(("#pending-versions", _pending_versions_html()))
    patches.append(("#pending-enrollments", _pending_enrollments_html()))
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


def _pending_versions_html() -> str:
    with _db() as session:
        pending = []
        actions, _ = storage.list_actions(session, page=1, per_page=500)
        for a in actions:
            v = storage.submitted_version(session, a.id)
            if v is not None:
                pending.append({"action": a, "version": v})
    return _render_partial("partials/pending_versions.html", pending=pending)


def _pending_enrollments_html() -> str:
    with _db() as session:
        enrollments, _ = storage.list_enrollments(
            session, state="requested", page=1, per_page=100
        )
        rows = [
            {"enrollment": e, "agent": storage.get_agent(session, e.agent_id)}
            for e in enrollments
        ]
    return _render_partial("partials/enrollment_queue.html", rows=rows)


@bp.post("/action-version/<version_id>/approve")
@admin_required(page=False)
def approve_version(version_id: str):
    notes = _data().get("notes")
    with _db() as session:
        from llmdmz.core.models import ActionVersion

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
            (f"#version-{version_id_str}-state", '<span class="badge active">active</span>'),
            (f"#action-{action.id}-state", '<span class="badge active">active</span>'),
        ])
    )


@bp.post("/action-version/<version_id>/reject")
@admin_required(page=False)
def reject_version(version_id: str):
    notes = _data().get("notes")
    with _db() as session:
        from llmdmz.core.models import ActionVersion

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
            (f"#version-{version_id_str}-state", '<span class="badge rejected">rejected</span>'),
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
            (f"#action-{action_id}-state", '<span class="badge withdrawn">withdrawn</span>'),
        ])
    )


# --- T4.15: enrollment queue + decisions ---------------------------------------


@bp.get("/partials/enrollments")
@admin_required(page=False, csrf=False)
def partial_enrollments():
    return sse_merge([("#pending-enrollments", _pending_enrollments_html())])


def _enrollment_or_404(session, enrollment_id):
    from llmdmz.core.models import Enrollment

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
    return sse_merge(_enrollment_patches())


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
    return sse_merge(_enrollment_patches())


@bp.post("/enrollment/<enrollment_id>/revoke")
@admin_required(page=False)
def revoke_enrollment(enrollment_id: str):
    with _db() as session:
        e = _enrollment_or_404(session, enrollment_id)
        storage.decide_enrollment(session, e, decision="revoked", decided_by=_actor())
        _audit(session, "enrollment.revoked", "enrollment", enrollment_id)
    return sse_merge(_enrollment_patches())


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


@bp.post("/action/<action_id>/enroll")
@admin_required(page=False)
def admin_enroll(action_id: str):
    """Admin-initiated enrollment (client + action)."""
    agent_id = _data().get("agent_id")
    with _db() as session:
        from llmdmz.core.models import Enrollment

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
    return sse_merge(_enrollment_patches())


# --- T4.17: agents tab ----------------------------------------------------------


@bp.get("/partials/agents")
@admin_required(page=False, csrf=False)
def partial_agents():
    page, per_page = _paged()
    with _db() as session:
        agents, total = storage.list_agents(session, page=page, per_page=per_page)
    return _render_partial(
        "partials/agents.html",
        agents=agents, page=page, per_page=per_page, total=total,
        target="#agents-list",
    )


@bp.post("/agents")
@admin_required(page=False)
def register_agent():
    """Register agent; plaintext key returned exactly once (#16)."""
    data = _data()
    name = (data.get("name") or "").strip()
    if not name:
        abort(400)
    is_client = data.get("is_client") in ("on", "true", True, 1)
    is_provider = data.get("is_provider") in ("on", "true", True, 1)
    if not (is_client or is_provider):
        abort(400)
    with _db() as session:
        agent, key = storage.register_agent(
            session, name=name, is_client=is_client, is_provider=is_provider
        )
        agent_id = agent.id
        _audit(session, "agent.registered", "agent", agent_id, {"name": name})
    # Delivery config is accepted but never echoed back in any listing.
    return _render_partial("partials/key_reveal.html", key=key, agent_id=agent_id,
        target="#agent-detail-region",
    )


@bp.get("/agents/<agent_id>")
@admin_required(page=False, csrf=False)
def agent_detail(agent_id: str):
    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        if agent is None:
            abort(404)
    return _render_partial("partials/agent_detail.html", agent=agent,
        target="#agent-detail-region",
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
        if "delivery_json" in data and data.get("delivery_json"):
            import json as _json

            try:
                agent.delivery_config = _json.loads(data["delivery_json"])
            except ValueError:
                abort(400)
        _audit(session, "agent.edited", "agent", agent_id)
    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        assert agent is not None
        html = _render_partial("partials/agent_detail.html", agent=agent, saved=True)
    return sse_merge([(f"#agent-{agent_id}-detail", html)])


@bp.post("/agents/<agent_id>/revoke-key")
@admin_required(page=False)
def agent_revoke_key(agent_id: str):
    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        if agent is None:
            abort(404)
        import secrets as _secrets

        from llmdmz.core.keys import hash_key
        agent.api_key_hash = hash_key("revoked:" + _secrets.token_urlsafe(32))
        _audit(session, "agent.key_revoked", "agent", agent_id)
    return sse_merge([(f"#agent-{agent_id}-key-state", "<em class=\"muted\">revoked</em>")])


@bp.post("/agents/<agent_id>/new-key")
@admin_required(page=False)
def agent_new_key(agent_id: str):
    with _db() as session:
        agent = storage.get_agent(session, agent_id)
        if agent is None:
            abort(404)
        key = storage.issue_key(session, agent)
        _audit(session, "agent.key_issued", "agent", agent_id)
    return _render_partial(
        "partials/key_reveal.html", key=key, agent_id=agent_id,
        target=f"#agent-{agent_id}-detail",
    )


# --- T4.19: request log ---------------------------------------------------------


@bp.get("/partials/log")
@admin_required(page=False, csrf=False)
def partial_log():
    page, per_page = _paged()
    outcome = request.args.get("outcome") or None
    action_id = request.args.get("action_id") or None
    with _db() as session:
        rows, total = storage.list_requests(
            session, action_id=action_id, outcome=outcome, page=page, per_page=per_page
        )
    return _render_partial(
        "partials/log.html",
        target="#log-list",
        rows=rows,
        page=page,
        per_page=per_page,
        total=total,
        outcome=outcome or "",
        action_id=action_id or "",
    )


@bp.get("/partials/request/<request_id>")
@admin_required(page=False, csrf=False)
def partial_request_detail(request_id: str):
    with _db() as session:
        row = storage.get_request(session, request_id)
        if row is None:
            abort(404)
        attempts = storage.list_attempts(session, request_id)
    return _render_partial("partials/request_detail.html", req=row, attempts=attempts,
        target="#request-detail",)


# --- T4.20: audit trail ---------------------------------------------------------


@bp.get("/partials/audit")
@admin_required(page=False, csrf=False)
def partial_audit():
    page, per_page = _paged()
    actor_id = request.args.get("actor_id") or None
    target_type = request.args.get("target_type") or None
    with _db() as session:
        rows, total = storage.list_audit_events(
            session, actor_id=actor_id, target_type=target_type, page=page, per_page=per_page
        )
    return _render_partial(
        "partials/audit.html",
        target="#audit-list",
        rows=rows,
        page=page,
        per_page=per_page,
        total=total,
        actor_id=actor_id or "",
        target_type=target_type or "",
    )

