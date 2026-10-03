"""Recording-provider transcripts for meetings (Feature 3).

ADDS to meetings (all nullable -- no existing row changes meaning):
  recording_bot_id        the provider's bot id; UNIQUE, and the ONLY key a
                          recording webhook is matched to a meeting by
  transcript_status       requesting | pending | received | failed | timed_out
  transcript_deadline_at  when a pending transcript stops being waited for
  summary_source          notes | transcript -- what the current summary used

Revision ID: 0049_meeting_recording
Revises: 0048_reengagement
"""

import sqlalchemy as sa
from alembic import op

revision = "0049_meeting_recording"
down_revision = "0048_reengagement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("recording_bot_id", sa.String(length=100), nullable=True))
    op.add_column("meetings", sa.Column("transcript_status", sa.String(length=20), nullable=True))
    op.add_column("meetings", sa.Column("transcript_deadline_at", sa.DateTime(timezone=True),
                                        nullable=True))
    op.add_column("meetings", sa.Column("summary_source", sa.String(length=20), nullable=True))
    op.create_index("ix_meetings_recording_bot_id", "meetings", ["recording_bot_id"],
                    unique=True)
    op.create_index("ix_meetings_transcript_status", "meetings", ["transcript_status"])


def downgrade() -> None:
    op.drop_index("ix_meetings_transcript_status", table_name="meetings")
    op.drop_index("ix_meetings_recording_bot_id", table_name="meetings")
    # batch mode: SQLite cannot DROP COLUMN in place.
    with op.batch_alter_table("meetings") as batch:
        batch.drop_column("summary_source")
        batch.drop_column("transcript_deadline_at")
        batch.drop_column("transcript_status")
        batch.drop_column("recording_bot_id")
