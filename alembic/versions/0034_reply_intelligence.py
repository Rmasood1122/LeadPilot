"""Feature 2 — reply intelligence engine.

ALTERS
  inbound_replies  reply_category, category_confidence, ai_next_action,
                   ai_draft_response, classified_at, reschedule_date

All nullable, no server defaults: every reply already on file stays exactly as
it is, and NULL reply_category means "never classified" rather than a wrong
category. The existing `classification` column is UNTOUCHED -- it drives the
M3 routing (unsubscribe / bounce / out-of-office) and is a different question
from this one. reply_category answers "what does the human do next?", which is
why both columns exist.

reschedule_date is a DATE, not a timestamp: a NOT_NOW follow-up is scheduled
for a day, and storing a spurious time-of-day would invite the follow-up sweep
to treat 00:00 UTC as a real send time.

Revision ID: 0034_reply_intelligence
Revises: 0033_pipeline_health
"""

import sqlalchemy as sa
from alembic import op

revision = "0034_reply_intelligence"
down_revision = "0033_pipeline_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inbound_replies",
                  sa.Column("reply_category", sa.String(length=20), nullable=True))
    op.add_column("inbound_replies",
                  sa.Column("category_confidence", sa.Float(), nullable=True))
    op.add_column("inbound_replies",
                  sa.Column("ai_next_action", sa.String(length=50), nullable=True))
    op.add_column("inbound_replies",
                  sa.Column("ai_draft_response", sa.Text(), nullable=True))
    op.add_column("inbound_replies",
                  sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("inbound_replies",
                  sa.Column("reschedule_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("inbound_replies") as batch:
        batch.drop_column("reschedule_date")
        batch.drop_column("classified_at")
        batch.drop_column("ai_draft_response")
        batch.drop_column("ai_next_action")
        batch.drop_column("category_confidence")
        batch.drop_column("reply_category")
