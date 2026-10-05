"""Reply kill switch: pause one contact / one account.

ADDS four nullable columns (no backfill, no default): leads.messaging_paused_at,
leads.messaging_paused_reason, users.messaging_paused_at,
users.messaging_paused_reason. NULL = not paused, so every existing row keeps
sending exactly as before.

Revision ID: 0072_messaging_pause
Revises: 0071_voice_interviews
"""

import sqlalchemy as sa
from alembic import op

revision = "0072_messaging_pause"
down_revision = "0071_voice_interviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("leads", "users"):
        op.add_column(table, sa.Column("messaging_paused_at", sa.DateTime(timezone=True),
                                       nullable=True))
        op.add_column(table, sa.Column("messaging_paused_reason", sa.String(20),
                                       nullable=True))


def downgrade() -> None:
    for table in ("leads", "users"):
        op.drop_column(table, "messaging_paused_reason")
        op.drop_column(table, "messaging_paused_at")
