"""M8-C5: production launch schema additions

Revision ID: 0011_m8c5
Revises: 0010_m8c4
Create Date: 2026-08-17 02:00:00.000000

Changes:
  1. webhook_targets table (user-registered outbound webhook destinations)
  2. webhook_deliveries table (delivery log with retry tracking)
  3. users.onboarding_state JSONB column
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_m8c5"
down_revision = "0010_m8c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. webhook_targets
    op.create_table(
        "webhook_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("secret_encrypted", sa.Text, nullable=True,
                  comment="Fernet-encrypted HMAC secret; never logged"),
        sa.Column("event_types", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("description", sa.Text, nullable=True),
    )
    # INTEGRATION REPAIR: user_id already carries index=True on the column above —
    # the explicit create_index duplicated it and failed on live PostgreSQL.
    # (This migration had never been applied; repaired in the combined build.)

    # 2. webhook_deliveries
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column("payload_json", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending",
                  comment="pending | delivered | failed | exhausted"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="5"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime, nullable=True),
        sa.Column("next_attempt_at", sa.DateTime, nullable=True),
        sa.Column("last_response_code", sa.Integer, nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"])
    op.create_index("ix_webhook_deliveries_created_at", "webhook_deliveries", ["created_at"])

    # 3. users.onboarding_state
    op.add_column("users", sa.Column(
        "onboarding_state", postgresql.JSONB, nullable=True,
        server_default="{}",
        comment="Tracks completed onboarding steps: {step_completed: [...], completed_at: ...}",
    ))


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_targets")
    op.drop_column("users", "onboarding_state")
