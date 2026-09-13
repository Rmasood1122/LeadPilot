"""Real-time reply authenticity (Feature A3).

ALTERS
  inbound_replies  authenticity_kind, authenticity_score, buyer_intent_score,
                   authenticity_confidence, authenticity_signals_json,
                   authenticity_scored_at

All nullable: replies stored before this feature are "not scored", which is a
different fact from "scored and found automated". No backfill -- scoring is
deterministic and can be re-run over history by POST
/crm/replies/{id}/authenticity/rescore when wanted.

Revision ID: 0043_reply_authenticity
Revises: 0042_activity_audit_trail
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_reply_authenticity"
down_revision = "0042_activity_audit_trail"
branch_labels = None
depends_on = None


def _columns() -> list[sa.Column]:
    return [
        sa.Column("authenticity_kind", sa.String(length=20), nullable=True),
        sa.Column("authenticity_score", sa.Float(), nullable=True),
        sa.Column("buyer_intent_score", sa.Float(), nullable=True),
        sa.Column("authenticity_confidence", sa.Float(), nullable=True),
        sa.Column("authenticity_signals_json", sa.JSON(), nullable=True),
        sa.Column("authenticity_scored_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    for column in _columns():
        op.add_column("inbound_replies", column)
    op.create_index("ix_inbound_replies_authenticity_kind", "inbound_replies",
                    ["authenticity_kind"])


def downgrade() -> None:
    op.drop_index("ix_inbound_replies_authenticity_kind", table_name="inbound_replies")
    with op.batch_alter_table("inbound_replies") as batch:
        for column in reversed(_columns()):
            batch.drop_column(column.name)
