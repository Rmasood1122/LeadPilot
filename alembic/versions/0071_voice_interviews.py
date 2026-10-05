"""Monthly style interviews.

CREATES voice_interviews: one row per interview (mode text|voice, status,
the answers until applied/discarded, the proposed profile, when the next one is
due). Create-only. user_id is ON DELETE CASCADE.

Revision ID: 0071_voice_interviews
Revises: 0070_linkedin_network_messages
"""

import sqlalchemy as sa
from alembic import op

revision = "0071_voice_interviews"
down_revision = "0070_linkedin_network_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "voice_interviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("answers_json", sa.JSON(), nullable=True),
        sa.Column("proposed_profile_json", sa.JSON(), nullable=True),
        sa.Column("voice_notice_ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_voice_interviews_user_id", "voice_interviews", ["user_id"])


def downgrade() -> None:
    op.drop_table("voice_interviews")
