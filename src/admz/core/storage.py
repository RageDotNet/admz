"""Storage module: the stable query/CRUD interface over the ORM.

All database access from blueprints/services goes through this module
(infra-v2.md); ORM queries are an implementation detail behind it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased, selectinload

from admz.core.keys import DEFAULT_PAYLOAD_CHARS, generate_agent_key, hash_key
from admz.core.models import (
    Action,
    ActionVersion,
    Agent,
    AuditEvent,
    DispatchAttempt,
    Enrollment,
    Request,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# --- agents ---------------------------------------------------------------


def register_agent(
    session: Session,
    *,
    name: str,
    is_client: bool,
    is_provider: bool,
    key_payload_chars: int = DEFAULT_PAYLOAD_CHARS,
) -> tuple[Agent, str]:
    """Register an agent; returns (row, plaintext key â€” reveal-once, #15)."""
    key = generate_agent_key(key_payload_chars)
    agent = Agent(
        name=name,
        api_key_hash=hash_key(key),
        is_client=is_client,
        is_provider=is_provider,
    )
    session.add(agent)
    session.flush()
    return agent, key


def issue_key(session: Session, agent: Agent, *, key_payload_chars: int = DEFAULT_PAYLOAD_CHARS) -> str:
    """Re-issue a bearer key (reveal-once)."""
    key = generate_agent_key(key_payload_chars)
    agent.api_key_hash = hash_key(key)
    session.flush()
    return key


def get_agent(session: Session, agent_id: str) -> Agent | None:
    return session.get(Agent, agent_id)


def find_agent_by_name(session: Session, name: str) -> Agent | None:
    return session.scalar(select(Agent).where(Agent.name == name))


def find_agent_by_key(session: Session, plaintext_key: str) -> Agent | None:
    return session.scalar(select(Agent).where(Agent.api_key_hash == hash_key(plaintext_key)))


def list_agents(
    session: Session, *, page: int = 1, per_page: int = 100
) -> tuple[list[Agent], int]:
    total = session.scalar(select(func.count()).select_from(Agent)) or 0
    rows = (
        session.scalars(
            select(Agent).order_by(Agent.name).offset((page - 1) * per_page).limit(per_page)
        )
        .unique()
        .all()
    )
    return list(rows), total


# --- actions & versions -----------------------------------------------------


def get_action(session: Session, action_id: str) -> Action | None:
    action = session.get(Action, action_id)
    if action is not None:
        _ = len(action.versions)  # ensure relationship loaded
    return action


def list_actions(
    session: Session,
    *,
    page: int = 1,
    per_page: int = 100,
    q: str | None = None,
    state: str | None = None,
) -> tuple[list[Action], int]:
    """Page actions. `state` and `q` are applied in SQL so `total` matches the page.

    `q` matches action id or the active version's description — not state
    (state is a separate filter).
    """
    stmt = select(Action)
    if state:
        stmt = stmt.where(Action.state == state)
    if q:
        like = f"%{q.lower()}%"
        active = aliased(ActionVersion)
        stmt = stmt.outerjoin(active, Action.active_version_id == active.id).where(
            or_(
                func.lower(Action.id).like(like),
                func.lower(
                    func.coalesce(func.json_extract(active.payload, "$.description"), "")
                ).like(like),
            )
        )
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.scalars(
            stmt.order_by(Action.id).offset((page - 1) * per_page).limit(per_page)
        )
        .unique()
        .all()
    )
    return list(rows), total


def next_version_number(session: Session, action: Action) -> int:
    current = session.scalar(
        select(func.max(ActionVersion.version_number)).where(ActionVersion.action_id == action.id)
    )
    return 1 if current is None else current + 1


def submitted_version(session: Session, action_id: str) -> ActionVersion | None:
    """The at-most-one pending `submitted` version of an action (#9)."""
    return session.scalar(
        select(ActionVersion)
        .where(ActionVersion.action_id == action_id, ActionVersion.state == "submitted")
        .order_by(ActionVersion.version_number.desc())
    )


def list_versions(session: Session, action_id: str) -> list[ActionVersion]:
    return list(
        session.scalars(
            select(ActionVersion)
            .where(ActionVersion.action_id == action_id)
            .order_by(ActionVersion.version_number)
        )
        .unique()
        .all()
    )


# --- enrollments ------------------------------------------------------------


def get_enrollment(session: Session, enrollment_id: str) -> Enrollment | None:
    return session.get(Enrollment, enrollment_id)


def find_enrollment(
    session: Session, *, agent_id: str, action_id: str
) -> Enrollment | None:
    return session.scalar(
        select(Enrollment).where(Enrollment.agent_id == agent_id, Enrollment.action_id == action_id)
    )


def list_enrollments(
    session: Session,
    *,
    action_id: str | None = None,
    agent_id: str | None = None,
    state: str | None = None,
    states: list[str] | None = None,
    action_q: str | None = None,
    client_q: str | None = None,
    order: str = "requested",
    page: int = 1,
    per_page: int = 100,
) -> tuple[list[Enrollment], int]:
    stmt = select(Enrollment)
    if client_q:
        stmt = stmt.join(Agent, Agent.id == Enrollment.agent_id).where(
            Agent.name.ilike(f"%{client_q}%")
        )
    if action_id:
        stmt = stmt.where(Enrollment.action_id == action_id)
    if action_q:
        stmt = stmt.where(Enrollment.action_id.ilike(f"%{action_q}%"))
    if agent_id:
        stmt = stmt.where(Enrollment.agent_id == agent_id)
    if states:
        stmt = stmt.where(Enrollment.state.in_(states))
    elif state:
        stmt = stmt.where(Enrollment.state == state)
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    if order == "decided":
        order_by = func.coalesce(Enrollment.decided_at, Enrollment.requested_at).desc()
    else:
        order_by = Enrollment.requested_at.desc()
    rows = (
        session.scalars(
            stmt.order_by(order_by)
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        .unique()
        .all()
    )
    return list(rows), total


# --- request logging ----------------------------------------------------------


def log_request(
    session: Session,
    *,
    action_id: str,
    agent_id: str,
    active_version_id: str | None,
    request_payload: dict,
    outcome: str,
    request_verdict: dict | None = None,
    response_payload: dict | None = None,
    finished: bool = True,
    created_at: datetime | None = None,
) -> Request:
    now = datetime.now(UTC)
    row = Request(
        action_id=action_id,
        agent_id=agent_id,
        active_version_id=active_version_id,
        request_payload=request_payload,
        request_verdict=request_verdict,
        response_payload=response_payload,
        outcome=outcome,
        created_at=created_at or now,
        finished_at=now if finished else None,
    )
    session.add(row)
    session.flush()
    return row


def set_request_state(session: Session, request_row: Request, *, outcome: str) -> None:
    """Update an in-flight request's outcome and commit it immediately.

    In-flight progress states (`received`, `arbiter_reviewing_request`,
    `dispatching`, `arbiter_reviewing_response`) are committed as they happen
    so the admin console's request log reflects live progress.
    """
    request_row.outcome = outcome
    session.commit()


def finish_request(
    session: Session,
    request_row: Request,
    *,
    outcome: str,
    response_payload: dict | None = None,
    request_verdict: dict | None = None,
) -> None:
    request_row.outcome = outcome
    request_row.finished_at = datetime.now(UTC)
    if response_payload is not None:
        request_row.response_payload = response_payload
    if request_verdict is not None:
        request_row.request_verdict = request_verdict


def log_attempt(
    session: Session,
    *,
    request_id: str,
    attempt_number: int,
    framing: dict,
    request_payload: dict | None = None,
    error_class: str | None = None,
    error_detail: str | None = None,
) -> DispatchAttempt:
    now = datetime.now(UTC)
    row = DispatchAttempt(
        request_id=request_id,
        attempt_number=attempt_number,
        framing=framing,
        request_payload=request_payload,
        error_class=error_class,
        error_detail=error_detail,
        started_at=now,
        finished_at=now,
    )
    session.add(row)
    session.flush()
    return row


def get_request(session: Session, request_id: str) -> Request | None:
    return session.scalar(
        select(Request)
        .options(selectinload(Request.agent), selectinload(Request.attempts))
        .where(Request.id == request_id)
    )


def list_requests(
    session: Session,
    *,
    action_id: str | None = None,
    agent_id: str | None = None,
    outcome: str | None = None,
    outcomes: list[str] | None = None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[Request], int]:
    stmt = select(Request).options(
        selectinload(Request.attempts),
        selectinload(Request.agent),
    )
    if action_id:
        stmt = stmt.where(Request.action_id == action_id)
    if agent_id:
        stmt = stmt.where(Request.agent_id == agent_id)
    if outcome:
        stmt = stmt.where(Request.outcome == outcome)
    if outcomes:
        stmt = stmt.where(Request.outcome.in_(outcomes))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.scalars(
            stmt.order_by(Request.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        .unique()
        .all()
    )
    return list(rows), total


def list_attempts(session: Session, request_id: str) -> list[DispatchAttempt]:
    return list(
        session.scalars(
            select(DispatchAttempt)
            .where(DispatchAttempt.request_id == request_id)
            .order_by(DispatchAttempt.attempt_number)
        )
        .all()
    )


# --- stats (#26) ----------------------------------------------------------------


def outcome_counts(session: Session) -> dict[str, int]:
    """All-time request totals by outcome token."""
    rows = session.execute(select(Request.outcome, func.count()).group_by(Request.outcome)).all()
    return {outcome: count for outcome, count in rows}


def requests_last_24h(session: Session) -> int:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    return session.scalar(
        select(func.count()).select_from(Request).where(Request.created_at >= cutoff)
    ) or 0


def requests_last_24h_at(session: Session, now: datetime) -> int:
    """Trailing-24h count relative to a fixed timestamp (test helper)."""
    cutoff = now - timedelta(hours=24)
    return session.scalar(
        select(func.count()).select_from(Request).where(Request.created_at >= cutoff)
    ) or 0


# --- audit ------------------------------------------------------------------


def list_audit_events(
    session: Session,
    *,
    actor_id: str | None = None,
    actor_q: str | None = None,
    target_type: str | None = None,
    events: list[str] | None = None,
    exclude_events: list[str] | None = None,
    page: int = 1,
    per_page: int = 50,
) -> tuple[list[AuditEvent], int]:
    stmt = select(AuditEvent)
    if actor_id:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    q = (actor_q or "").strip()
    if q:
        name_ids = list(
            session.scalars(select(Agent.id).where(Agent.name.ilike(f"%{q}%"))).all()
        )
        actor_match = [AuditEvent.actor_id.ilike(f"%{q}%")]
        if name_ids:
            actor_match.append(AuditEvent.actor_id.in_(name_ids))
        stmt = stmt.where(or_(*actor_match))
    if target_type:
        stmt = stmt.where(AuditEvent.target_type == target_type)
    if events:
        stmt = stmt.where(AuditEvent.event.in_(events))
    if exclude_events:
        stmt = stmt.where(AuditEvent.event.notin_(exclude_events))
    total = session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        session.scalars(
            stmt.order_by(AuditEvent.occurred_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )
        .all()
    )
    return list(rows), total


def clamp_page(
    page: object,
    per_page: object,
    *,
    max_per_page: int = 500,
    default_per_page: int = 100,
) -> tuple[int, int]:
    """Clamp pagination params - invalid values clamp, not error (#18)."""

    def _int(value: object, fallback: int) -> int:
        try:
            return int(value)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return fallback

    page_n = max(1, _int(page, 1))
    per_page_n = min(max(1, _int(per_page, default_per_page)), max_per_page)
    return page_n, per_page_n



# --- Version decisions (used by admin approval flows; #7/#8/#9) ----------------


def decide_version(
    session: Session,
    version: ActionVersion,
    *,
    decision: str,  # approved | rejected
    decided_by: str,
    notes: str | None = None,
) -> Action:
    """Apply a reviewer decision to a submitted version.

    Approve swaps atomically: any current active version becomes ``superseded``
    and the action becomes ``active`` (withdrawn -> active reactivation included,
    #8). Reject is terminal for that version; the action returns to ``pending``
    if it has no other active version. Caller commits + audits.
    """
    action = version.action
    if decision == "approved":
        current = action.active_version
        if current is not None and current.id != version.id:
            current.state = "superseded"
        version.state = "active"
        action.active_version_id = version.id
        action.state = "active"
    else:
        version.state = "rejected"
        if action.active_version_id is None:
            action.state = "pending"
    version.decided_at = datetime.now(tz=UTC)
    version.decided_by = decided_by
    version.decision_notes = notes
    session.flush()
    return action


def decide_enrollment(
    session: Session,
    enrollment: Enrollment,
    *,
    decision: str,  # approved | rejected | revoked | reset
    decided_by: str,
    notes: str | None = None,
) -> Enrollment:
    """Apply an admin decision to an enrollment (T4.15, #11).

    ``reset`` deletes the rejected row so the client may re-request (#11).
    Caller commits + audits.
    """
    now = datetime.now(tz=UTC)
    if decision == "approved":
        enrollment.state = "enrolled"
        enrollment.decided_at = now
        enrollment.decided_by = decided_by
        enrollment.decision_notes = notes
    elif decision in ("rejected", "revoked"):
        enrollment.state = decision if decision == "rejected" else "revoked"
        enrollment.decided_at = now
        enrollment.decided_by = decided_by
        enrollment.decision_notes = notes
        if decision == "revoked":
            enrollment.revoked_at = now
    elif decision == "reset":
        session.delete(enrollment)
        session.flush()
        return enrollment
    else:
        raise ValueError(f"unknown enrollment decision: {decision}")
    session.flush()
    return enrollment
