"""v2 baseline: full schema per clarification #13 (single initial migration, #32).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-18
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("api_key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("is_client", sa.Boolean(), nullable=False),
        sa.Column("is_provider", sa.Boolean(), nullable=False),
        sa.Column("disabled", sa.Boolean(), nullable=False),
        sa.Column("delivery_config", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "actions",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "owner_agent_id", sa.String(36), sa.ForeignKey("agents.id"), nullable=False
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column(
            "active_version_id", sa.String(36), sa.ForeignKey("action_versions.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_actions_owner_agent_id", "actions", ["owner_agent_id"])
    op.create_table(
        "action_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "action_id", sa.String(255), sa.ForeignKey("actions.id"), nullable=False
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("action_id", "version_number"),
    )
    op.create_index("ix_action_versions_action_id", "action_versions", ["action_id"])
    op.create_table(
        "enrollments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("action_id", sa.String(255), sa.ForeignKey("actions.id"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("agent_id", "action_id"),
    )
    op.create_index("ix_enrollments_agent", "enrollments", ["agent_id"])
    op.create_index("ix_enrollments_action", "enrollments", ["action_id"])
    op.create_table(
        "requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("action_id", sa.String(255), nullable=False),
        sa.Column("agent_id", sa.String(36), nullable=False),
        sa.Column("active_version_id", sa.String(36), nullable=True),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("request_verdict", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_requests_action_created", "requests", ["action_id", "created_at"])
    op.create_index("ix_requests_agent_created", "requests", ["agent_id", "created_at"])
    op.create_index("ix_requests_created", "requests", ["created_at"])
    op.create_table(
        "dispatch_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "request_id", sa.String(36), sa.ForeignKey("requests.id"), nullable=False
        ),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("framing", sa.JSON(), nullable=False),
        sa.Column("error_class", sa.String(32), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_dispatch_attempts_request_id", "dispatch_attempts", ["request_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_type", sa.String(8), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.String(255), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=True),
    )
    op.create_index("ix_audit_target", "audit_events", ["target_type", "target_id"])
    op.create_index("ix_audit_occurred", "audit_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("dispatch_attempts")
    op.drop_table("requests")
    op.drop_table("enrollments")
    op.drop_table("action_versions")
    op.drop_table("actions")
    op.drop_table("agents")

