"""Positive reply classification (Part 1, Feature 1).

ALTERS
  inbound_replies  intent_label, intent_confidence, intent_reason,
                   intent_source, intent_at

WHY NEW COLUMNS AND NOT `reply_category`. `reply_category` (0034) already
drives the reply-intelligence drafts and its four values are read by the CRM
replies UI; widening its value set would silently change that feature's
meaning. This is a different question -- "was this reply POSITIVE?" -- with
its own five-value taxonomy (interested | neutral | objection | not_now |
unsubscribe) and its own confidence, so it gets its own columns.

All nullable: a reply stored before this revision is "not classified", which
is a different fact from "classified as neutral". No backfill; POST
/crm/replies/{id}/intent/reclassify re-runs one on demand.

Revision ID: 0053_reply_intent
Revises: 0052_auth_sessions
"""

import sqlalchemy as sa
from alembic import op

revision = "0053_reply_intent"
down_revision = "0052_auth_sessions"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("intent_label", sa.String(length=20), nullable=True),
        sa.Column("intent_confidence", sa.Float(), nullable=True),
        sa.Column("intent_reason", sa.String(length=300), nullable=True),
        sa.Column("intent_source", sa.String(length=10), nullable=True),
        sa.Column("intent_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    for column in _columns():
        op.add_column("inbound_replies", column)
    op.create_index("ix_inbound_replies_intent_label", "inbound_replies", ["intent_label"])


def downgrade() -> None:
    op.drop_index("ix_inbound_replies_intent_label", table_name="inbound_replies")
    with op.batch_alter_table("inbound_replies") as batch:
        for column in reversed(_columns()):
            batch.drop_column(column.name)
