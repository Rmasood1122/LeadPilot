"""Re-engagement memory -- "not now" is not "never" (Part 1, Feature 7).

CREATES
  reengagement_plans   one row per "not now" reply: the reason the prospect
                       gave IN THEIR OWN WORDS, the date they named if they
                       named one, when to come back, and what happened when
                       the day arrived.

WHY A NEW TABLE AND NOT reengagement_attempts (0048). That table is the
once-per-enrollment CLAIM for the opt-in post-sequence sweep -- its whole
purpose is the UNIQUE(enrollment_id) that stops a retry sending twice, and it
carries no reason and no future date. This is a different object with a
different lifetime: it is created by a reply, it can outlive the enrollment
(and the sequence) that produced it, a person can move or cancel it, and it is
the thing the prospect's own words live on. Bolting a reason and a due date
onto the claim row would tie a 90-day memory to a table designed to be
consumed once and forgotten.

WHY THE REASON IS STORED AS TEXT AND A KIND. The kind (budget, contract,
timing, ...) is what the UI groups and filters by; the text is what the
follow-up message quotes. A hook built on their sentence survives being read
back to them nine months later; a paraphrase does not.

UNIQUE (source_reply_id) makes this idempotent by construction: a webhook
retry, a re-classification, or two overlapping sweeps cannot produce two plans
for one reply.

Revision ID: 0059_reengagement_memory
Revises: 0058_inbox_handling
"""

import sqlalchemy as sa
from alembic import op

revision = "0059_reengagement_memory"
down_revision = "0058_inbox_handling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reengagement_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("source_reply_id", sa.Uuid(), nullable=True),
        sa.Column("reason_kind", sa.String(length=30), nullable=True),
        sa.Column("reason_text", sa.String(length=500), nullable=True),
        sa.Column("stated_return_on", sa.Date(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'scheduled'")),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=200), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_reason", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reengagement_plans"),
        sa.UniqueConstraint("source_reply_id", name="reengagement_plan_reply"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_reengagement_plans_lead_id_leads"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_reengagement_plans_user_id_users"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL",
                                name="fk_reengagement_plans_strategy_id_strategies"),
        sa.ForeignKeyConstraint(["source_reply_id"], ["inbound_replies.id"],
                                ondelete="SET NULL",
                                name="fk_reengagement_plans_source_reply_id_inbound_replies"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL",
                                name="fk_reengagement_plans_message_id_messages"),
    )
    op.create_index("ix_reengagement_plans_lead_id", "reengagement_plans", ["lead_id"])
    op.create_index("ix_reengagement_plans_user_id", "reengagement_plans", ["user_id"])
    op.create_index("ix_reengagement_plans_due_at", "reengagement_plans", ["due_at"])
    op.create_index("ix_reengagement_plans_status", "reengagement_plans", ["status"])


def downgrade() -> None:
    op.drop_index("ix_reengagement_plans_status", table_name="reengagement_plans")
    op.drop_index("ix_reengagement_plans_due_at", table_name="reengagement_plans")
    op.drop_index("ix_reengagement_plans_user_id", table_name="reengagement_plans")
    op.drop_index("ix_reengagement_plans_lead_id", table_name="reengagement_plans")
    op.drop_table("reengagement_plans")
