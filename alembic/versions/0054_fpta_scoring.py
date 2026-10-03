"""Fit / Problem / Timing / Access scoring (Part 1, Feature 2).

ALTERS
  leads  fpta_fit, fpta_problem, fpta_timing, fpta_access, fpta_overall,
         fpta_reasons_json, fpta_method, fpta_scored_at

WHY NOT REUSE `ai_booking_likelihood`. That column is ONE number answering one
question ("will they book?"). F-P-T-A answers four, and the whole point is that
a lead can be a perfect fit with no timing, or desperate with no way to reach
them -- facts a single number erases. The two live side by side; neither reads
the other's columns.

All nullable: a lead sourced before this revision is "not scored", which sorts
last rather than reading as a zero. `fpta_overall` is indexed because the lead
list offers it as a sort.

Revision ID: 0054_fpta_scoring
Revises: 0053_reply_intent
"""

import sqlalchemy as sa
from alembic import op

revision = "0054_fpta_scoring"
down_revision = "0053_reply_intent"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("fpta_fit", sa.Integer(), nullable=True),
        sa.Column("fpta_problem", sa.Integer(), nullable=True),
        sa.Column("fpta_timing", sa.Integer(), nullable=True),
        sa.Column("fpta_access", sa.Integer(), nullable=True),
        sa.Column("fpta_overall", sa.Integer(), nullable=True),
        sa.Column("fpta_reasons_json", sa.JSON(), nullable=True),
        sa.Column("fpta_method", sa.String(length=10), nullable=True),
        sa.Column("fpta_scored_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    for column in _columns():
        op.add_column("leads", column)
    op.create_index("ix_leads_fpta_overall", "leads", ["fpta_overall"])


def downgrade() -> None:
    op.drop_index("ix_leads_fpta_overall", table_name="leads")
    with op.batch_alter_table("leads") as batch:
        for column in reversed(_columns()):
            batch.drop_column(column.name)
