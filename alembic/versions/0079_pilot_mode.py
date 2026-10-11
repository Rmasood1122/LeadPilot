"""F09 30-Day Pilot Mode: success criteria on day 1, weekly scorecard, verdict.

CREATES
  pilots            one row per 30-day pilot of an account: dates, the
                    success criteria (locked at the start), campaign scope,
                    status, and -- once ended -- the verdict with an aggregate
                    snapshot of the F08 meetings ledger. `active_owner_id` is
                    UNIQUE and set only while the pilot is active: one active
                    pilot per account, enforced by the schema.
  pilot_scorecards  one row per (pilot, week) weekly scorecard email; UNIQUE
                    (pilot_id, week) is the idempotency key the sweep claims
                    before it sends.

NOTHING HERE TOUCHES BILLING (users.plan, billing_subscriptions). See
docs/features/f09-pilot-mode.md.

Create-only; types work on SQLite (tests) and PostgreSQL (JSON, not JSONB).
DOWNGRADE drops both tables: pilot history, verdicts and the scorecard log are
lost. Nothing else is touched (the numbers they summarise live in their own
tables and are recomputable with the F08 ledger for the same dates).

Revision ID: 0079_pilot_mode
Revises: 0078_spend_guard
"""

import sqlalchemy as sa
from alembic import op

revision = "0079_pilot_mode"
down_revision = "0078_spend_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pilots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("active_owner_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'active'")),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criteria_json", sa.JSON(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("strategy_ids_json", sa.JSON(), nullable=True),
        sa.Column("scorecard_emails", sa.Boolean(), server_default=sa.true(),
                  nullable=False),
        sa.Column("plan_at_start", sa.String(length=30), nullable=True),
        sa.Column("plan_at_end", sa.String(length=30), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=20), nullable=True),
        sa.Column("verdict_json", sa.JSON(), nullable=True),
        sa.Column("verdict_emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verdict_email_attempts", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("verdict_email_status", sa.String(length=20), nullable=True),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_pilots"),
        sa.UniqueConstraint("active_owner_id", name="uq_pilots_active_owner_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_pilots_user_id_users"),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_pilots_started_by_user_id_users"),
    )
    op.create_index("ix_pilots_user_id", "pilots", ["user_id"])
    op.create_index("ix_pilots_status", "pilots", ["status"])

    op.create_table(
        "pilot_scorecards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("pilot_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("week", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'sending'")),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=300), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_pilot_scorecards"),
        sa.UniqueConstraint("pilot_id", "week", name="uq_pilot_scorecard_week"),
        sa.ForeignKeyConstraint(["pilot_id"], ["pilots.id"], ondelete="CASCADE",
                                name="fk_pilot_scorecards_pilot_id_pilots"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_pilot_scorecards_user_id_users"),
    )
    op.create_index("ix_pilot_scorecards_pilot_id", "pilot_scorecards", ["pilot_id"])
    op.create_index("ix_pilot_scorecards_user_id", "pilot_scorecards", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_pilot_scorecards_user_id", table_name="pilot_scorecards")
    op.drop_index("ix_pilot_scorecards_pilot_id", table_name="pilot_scorecards")
    op.drop_table("pilot_scorecards")
    op.drop_index("ix_pilots_status", table_name="pilots")
    op.drop_index("ix_pilots_user_id", table_name="pilots")
    op.drop_table("pilots")
