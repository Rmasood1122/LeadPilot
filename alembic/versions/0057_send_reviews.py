"""Human review queue for high-risk sends (Part 1, Feature 5).

CREATES
  send_reviews   one row per message held for human approval, carrying the
                 EXACT rendered subject and body the reviewer approves, the
                 triggers that held it, and the decision.

NO COLUMN CHANGE FOR THE NEW MESSAGE STATUS. `messages.status` is a
VARCHAR-backed enum (models._enum: native_enum=False), so adding
MessageStatus.AWAITING_REVIEW is a data-free addition -- the same technique
LeadStatus.PROPOSAL_SENT and OPPORTUNITY used.

WHY THE COPY IS SNAPSHOTTED HERE and not just read from `messages` at review
time: the reviewer is approving specific words. A later re-render (a different
personalization pass, an edited step brief) must not change what was approved
without a new review. The send path compares the approved snapshot against the
message it is about to transmit and re-queues if they differ.

Revision ID: 0057_send_reviews
Revises: 0056_mailbox_health
"""

import sqlalchemy as sa
from alembic import op

revision = "0057_send_reviews"
down_revision = "0056_mailbox_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "send_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("triggers_json", sa.JSON(), nullable=True),
        sa.Column("subject_snapshot", sa.String(length=500), nullable=True),
        sa.Column("body_snapshot", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("decided_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
        sa.Column("edited_subject", sa.String(length=500), nullable=True),
        sa.Column("edited_body", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_send_reviews"),
        sa.UniqueConstraint("message_id", name="send_review_message"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE",
                                name="fk_send_reviews_message_id_messages"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL",
                                name="fk_send_reviews_lead_id_leads"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_send_reviews_user_id_users"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_send_reviews_decided_by_user_id_users"),
    )
    op.create_index("ix_send_reviews_status", "send_reviews", ["status"])
    op.create_index("ix_send_reviews_user_id", "send_reviews", ["user_id"])
    op.create_index("ix_send_reviews_lead_id", "send_reviews", ["lead_id"])


def downgrade() -> None:
    op.drop_index("ix_send_reviews_lead_id", table_name="send_reviews")
    op.drop_index("ix_send_reviews_user_id", table_name="send_reviews")
    op.drop_index("ix_send_reviews_status", table_name="send_reviews")
    op.drop_table("send_reviews")
