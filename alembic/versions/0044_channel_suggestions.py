"""Cross-channel stagnation suggestions (Feature A4).

CREATES
  channel_suggestions  "no reply after N sends on this channel -- try that one",
                       and what was decided (accepted / auto_switched / dismissed)

The unified conversation thread is deliberately NOT a table: it is assembled
from messages, inbound_replies, calls, calendar_bookings and meetings at read
time (app/services/conversation_thread.py), so it can never disagree with them.

Revision ID: 0044_channel_suggestions
Revises: 0043_reply_authenticity
"""

import sqlalchemy as sa
from alembic import op

revision = "0044_channel_suggestions"
down_revision = "0043_reply_authenticity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("enrollment_id", sa.Uuid(), nullable=True),
        sa.Column("from_channel", sa.String(length=20), nullable=False),
        sa.Column("to_channel", sa.String(length=20), nullable=False),
        sa.Column("sends_without_reply", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="suggested", nullable=False),
        sa.Column("switched_message_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_channel_suggestions"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_channel_suggestions_lead_id_leads"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_channel_suggestions_user_id_users"),
        sa.ForeignKeyConstraint(["enrollment_id"], ["sequence_enrollments.id"],
                                ondelete="SET NULL",
                                name="fk_channel_suggestions_enrollment_id_sequence_enrollments"),
        sa.ForeignKeyConstraint(["switched_message_id"], ["messages.id"], ondelete="SET NULL",
                                name="fk_channel_suggestions_switched_message_id_messages"),
    )
    op.create_index("ix_channel_suggestions_user_id", "channel_suggestions", ["user_id"])
    op.create_index("ix_channel_suggestions_lead_status", "channel_suggestions",
                    ["lead_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_channel_suggestions_lead_status", table_name="channel_suggestions")
    op.drop_index("ix_channel_suggestions_user_id", table_name="channel_suggestions")
    op.drop_table("channel_suggestions")
