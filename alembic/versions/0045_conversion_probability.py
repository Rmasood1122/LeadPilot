"""Live conversion probability and kill-signal state (Feature A5).

ALTERS
  leads  conversion_probability, conversion_probability_at, engagement_state,
         kill_signal, conversion_factors_json

All nullable: a lead never estimated behaves exactly as before (engagement_state
NULL reads as active), so no backfill is needed and no running sequence changes
behaviour on deploy.

Revision ID: 0045_conversion_probability
Revises: 0044_channel_suggestions
"""

import sqlalchemy as sa
from alembic import op

revision = "0045_conversion_probability"
down_revision = "0044_channel_suggestions"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("conversion_probability", sa.Float(), nullable=True),
        sa.Column("conversion_probability_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engagement_state", sa.String(length=20), nullable=True),
        sa.Column("kill_signal", sa.String(length=50), nullable=True),
        sa.Column("conversion_factors_json", sa.JSON(), nullable=True),
    ]


def upgrade() -> None:
    for column in _columns():
        op.add_column("leads", column)
    op.create_index("ix_leads_engagement_state", "leads", ["engagement_state"])


def downgrade() -> None:
    op.drop_index("ix_leads_engagement_state", table_name="leads")
    with op.batch_alter_table("leads") as batch:
        for column in reversed(_columns()):
            batch.drop_column(column.name)
