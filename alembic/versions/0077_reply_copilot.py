"""F04 Reply Copilot: grounded, claim-verified answers to inbound replies.

CREATES
  reply_drafts            one draft per inbound reply (UNIQUE reply_id), its
                          grounding, claim-verification flags, the decision
                          (approve / copy / discard), edit tracking and the
                          message an approval queued.
  reply_copilot_settings  one row per account: the auto-send opt-in.

A DRAFT IS NOT A SEND. Approving an email draft creates an ordinary `messages`
row (origin "reply_copilot") that goes through send_message_impl like every
other message. See docs/features/f04-reply-copilot.md.

Create-only; types work on SQLite (tests) and PostgreSQL (JSON, not JSONB).
DOWNGRADE drops both tables: the drafts and the opt-in are lost. Messages an
approval queued are ordinary `messages` rows and are not touched.

Revision ID: 0077_reply_copilot
Revises: 0076_quickstart
"""

import sqlalchemy as sa
from alembic import op

revision = "0077_reply_copilot"
down_revision = "0076_quickstart"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reply_drafts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reply_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("intent", sa.String(length=20), nullable=False),
        sa.Column("meeting_time_request", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("draft_subject", sa.String(length=500), nullable=True),
        sa.Column("draft_body", sa.Text(), nullable=False),
        sa.Column("final_subject", sa.String(length=500), nullable=True),
        sa.Column("final_body", sa.Text(), nullable=True),
        sa.Column("edited", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("claim_flags_json", sa.JSON(), nullable=True),
        sa.Column("grounding_json", sa.JSON(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("send_result", sa.String(length=60), nullable=True),
        sa.Column("auto_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reply_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reply_drafts"),
        sa.UniqueConstraint("reply_id", name="uq_reply_drafts_reply_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_reply_drafts_user_id_users"),
        sa.ForeignKeyConstraint(["reply_id"], ["inbound_replies.id"], ondelete="CASCADE",
                                name="fk_reply_drafts_reply_id_inbound_replies"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_reply_drafts_lead_id_leads"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL",
                                name="fk_reply_drafts_strategy_id_strategies"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL",
                                name="fk_reply_drafts_message_id_messages"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_reply_drafts_decided_by_user_id_users"),
    )
    op.create_index("ix_reply_drafts_user_id", "reply_drafts", ["user_id"])
    op.create_index("ix_reply_drafts_lead_id", "reply_drafts", ["lead_id"])
    op.create_index("ix_reply_drafts_status", "reply_drafts", ["status"])

    op.create_table(
        "reply_copilot_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("auto_send_meeting_time", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reply_copilot_settings"),
        sa.UniqueConstraint("user_id", name="uq_reply_copilot_settings_user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_reply_copilot_settings_user_id_users"),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_reply_copilot_settings_updated_by_user_id_users"),
    )


def downgrade() -> None:
    op.drop_table("reply_copilot_settings")
    op.drop_index("ix_reply_drafts_status", table_name="reply_drafts")
    op.drop_index("ix_reply_drafts_lead_id", table_name="reply_drafts")
    op.drop_index("ix_reply_drafts_user_id", table_name="reply_drafts")
    op.drop_table("reply_drafts")
