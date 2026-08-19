"""Append-only audit trail writer (T1.9)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from llmdmz.core.models import AuditEvent

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def audit(
    session: Session,
    *,
    actor_type: str,  # agent | admin | system
    actor_id: str,
    event: str,
    target_type: str,
    target_id: str,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one audit_events row; the caller commits the session."""
    row = AuditEvent(
        actor_type=actor_type,
        actor_id=actor_id,
        event=event,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    session.add(row)
    return row
