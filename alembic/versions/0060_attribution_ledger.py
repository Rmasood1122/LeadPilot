"""Transparent attribution ledger (Part 1, Feature 8).

CREATES
  attribution_entries   one row per positive outcome, naming the exact touch
                        the prospect was responding to: which message, on which
                        channel, at which step, how long after it landed -- and
                        HOW that was worked out, with the evidence.

WHY A LEDGER AND NOT A COLUMN ON `outcomes`. `outcomes` is the immutable event
log the learning loop reads; it already has a nullable `message_id`, which is
the message that CAUSED the event only for events the send path itself writes
(sent, opened, clicked). A booking that arrives by webhook three days later has
no message_id and no way to get one at write time. Attribution is a separate,
LATER, re-computable judgement -- and one that has to record its own
uncertainty, which an immutable log row cannot.

WHY THE METHOD AND CONFIDENCE ARE STORED. "This meeting came from step 2 on
LinkedIn" is worth very different amounts depending on whether the prospect
literally replied to that message or whether it was simply the last thing we
sent before they booked. A ledger that hides which of those happened is a
ledger that will eventually be believed when it should not be.

UNIQUE (outcome_kind, outcome_id) makes the sweep idempotent by construction:
it can run every fifteen minutes forever and never double-credit.

Revision ID: 0060_attribution_ledger
Revises: 0059_reengagement_memory
"""

import sqlalchemy as sa
from alembic import op

revision = "0060_attribution_ledger"
down_revision = "0059_reengagement_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "attribution_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("outcome_kind", sa.String(length=30), nullable=False),
        sa.Column("outcome_id", sa.Uuid(), nullable=True),
        sa.Column("outcome_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=True),
        sa.Column("step_no", sa.Integer(), nullable=True),
        sa.Column("message_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hours_to_outcome", sa.Float(), nullable=True),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("subject_snapshot", sa.String(length=500), nullable=True),
        sa.Column("body_snapshot", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_attribution_entries"),
        sa.UniqueConstraint("outcome_kind", "outcome_id", name="attribution_outcome"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL",
                                name="fk_attribution_entries_lead_id_leads"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_attribution_entries_user_id_users"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL",
                                name="fk_attribution_entries_strategy_id_strategies"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL",
                                name="fk_attribution_entries_message_id_messages"),
    )
    op.create_index("ix_attribution_entries_lead_id", "attribution_entries", ["lead_id"])
    op.create_index("ix_attribution_entries_user_id", "attribution_entries", ["user_id"])
    op.create_index("ix_attribution_entries_strategy_id", "attribution_entries",
                    ["strategy_id"])
    op.create_index("ix_attribution_entries_outcome_at", "attribution_entries",
                    ["outcome_at"])


def downgrade() -> None:
    op.drop_index("ix_attribution_entries_outcome_at", table_name="attribution_entries")
    op.drop_index("ix_attribution_entries_strategy_id", table_name="attribution_entries")
    op.drop_index("ix_attribution_entries_user_id", table_name="attribution_entries")
    op.drop_index("ix_attribution_entries_lead_id", table_name="attribution_entries")
    op.drop_table("attribution_entries")
