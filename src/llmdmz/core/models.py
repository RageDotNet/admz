"""SQLAlchemy 2.x declarative models — authoritative ERD per clarification #13."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_client: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_provider: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    delivery_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActionVersion(Base):
    __tablename__ = "action_versions"
    __table_args__ = (UniqueConstraint("action_id", "version_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    action_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("actions.id"), index=True, nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # submitted | active | rejected | superseded
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="submitted")
    # description, both schemas, instruction blocks (schemas-v2.md)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    action = relationship(
        "Action", back_populates="versions", foreign_keys=[action_id]
    )


class Action(Base):
    __tablename__ = "actions"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    owner_agent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agents.id"), index=True, nullable=False
    )
    # pending | active | withdrawn (canonical states, system-prd-v2.md)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    active_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("action_versions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    versions = relationship(
        "ActionVersion", back_populates="action", foreign_keys=[ActionVersion.action_id]
    )

    @property
    def active_version(self) -> ActionVersion | None:
        for v in self.versions:
            if v.id == self.active_version_id:
                return v
        return None


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("agent_id", "action_id"),
        Index("ix_enrollments_agent", "agent_id"),
        Index("ix_enrollments_action", "action_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id"), nullable=False)
    action_id: Mapped[str] = mapped_column(String(255), ForeignKey("actions.id"), nullable=False)
    # requested | enrolled | rejected | revoked
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="requested")
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = (
        Index("ix_requests_action_created", "action_id", "created_at"),
        Index("ix_requests_agent_created", "agent_id", "created_at"),
        Index("ix_requests_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    action_id: Mapped[str] = mapped_column(String(255), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    active_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # snapshot
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_verdict: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # completed | request_schema_invalid | arbiter_rejected | provider_failed |
    # arbiter_unavailable | internal_error
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DispatchAttempt(Base):
    __tablename__ = "dispatch_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("requests.id"), index=True, nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    framing: Mapped[dict] = mapped_column(JSON, nullable=False)
    # Per-attempt payloads for operator debugging (both set by the pipeline:
    # the request this attempt delivered, and the candidate response the
    # provider returned — kept even when schema/arbiter rejects it).
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_target", "target_type", "target_id"),
        Index("ix_audit_occurred", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # agent | admin | system
    actor_type: Mapped[str] = mapped_column(String(8), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # stable token, e.g. version.approved, enrollment.revoked, action.withdrawn
    event: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

