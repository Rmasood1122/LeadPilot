"""Opt-in post-sequence re-engagement (Feature 5).

ADDS
  strategies.reengagement_enabled      per-campaign toggle, FALSE by default
  strategies.reengagement_delay_days   wait after the last send (default 30)
  strategies.reengagement_daily_cap    this feature's own caps (10 / 25),
  strategies.reengagement_weekly_cap   separate from the channel daily cap
  messages.origin                      NULL for ordinary steps; "reengagement"

CREATES
  reengagement_attempts  one row per re-engaged enrollment, UNIQUE
                         (enrollment_id) -- the schema-level guarantee that a
                         lead is re-engaged at most once per enrollment

Every added column carries a server_default (or is nullable), so the ALTERs are
safe on tables that already hold rows, and every existing campaign lands with
re-engagement OFF.

Revision ID: 0048_reengagement
Revises: 0047_sequence_reviews
"""

import sqlalchemy as sa
from alembic import op

revision = "0048_reengagement"
down_revision = "0047_sequence_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategies", sa.Column(
        "reengagement_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("strategies", sa.Column(
        "reengagement_delay_days", sa.Integer(), server_default=sa.text("30"), nullable=False))
    op.add_column("strategies", sa.Column(
        "reengagement_daily_cap", sa.Integer(), server_default=sa.text("10"), nullable=False))
    op.add_column("strategies", sa.Column(
        "reengagement_weekly_cap", sa.Integer(), server_default=sa.text("25"), nullable=False))

    op.add_column("messages", sa.Column("origin", sa.String(length=20), nullable=True))
    op.create_index("ix_messages_origin", "messages", ["origin"])

    op.create_table(
        "reengagement_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("enrollment_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("detail", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reengagement_attempts"),
        sa.UniqueConstraint("enrollment_id", name="reengagement_enrollment"),
        sa.ForeignKeyConstraint(
            ["enrollment_id"], ["sequence_enrollments.id"], ondelete="CASCADE",
            name="fk_reengagement_attempts_enrollment_id_sequence_enrollments"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_reengagement_attempts_lead_id_leads"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE",
                                name="fk_reengagement_attempts_strategy_id_strategies"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL",
                                name="fk_reengagement_attempts_message_id_messages"),
    )
    op.create_index("ix_reengagement_attempts_lead_id", "reengagement_attempts", ["lead_id"])
    op.create_index("ix_reengagement_attempts_strategy_id", "reengagement_attempts",
                    ["strategy_id"])


def downgrade() -> None:
    op.drop_index("ix_reengagement_attempts_strategy_id", table_name="reengagement_attempts")
    op.drop_index("ix_reengagement_attempts_lead_id", table_name="reengagement_attempts")
    op.drop_table("reengagement_attempts")

    op.drop_index("ix_messages_origin", table_name="messages")
    # batch mode: SQLite cannot DROP COLUMN in place; on PostgreSQL this is a
    # plain ALTER TABLE.
    with op.batch_alter_table("messages") as batch:
        batch.drop_column("origin")
    with op.batch_alter_table("strategies") as batch:
        batch.drop_column("reengagement_weekly_cap")
        batch.drop_column("reengagement_daily_cap")
        batch.drop_column("reengagement_delay_days")
        batch.drop_column("reengagement_enabled")
