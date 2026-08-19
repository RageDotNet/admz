"""Dispatch attempts: per-attempt request/response payloads for debugging.

Revision ID: 0002_attempt_payloads
Revises: 0001_baseline
Create Date: 2026-08-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_attempt_payloads"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dispatch_attempts",
        sa.Column("request_payload", sa.JSON(), nullable=True),
    )
    op.add_column(
        "dispatch_attempts",
        sa.Column("response_payload", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("dispatch_attempts", "response_payload")
    op.drop_column("dispatch_attempts", "request_payload")
