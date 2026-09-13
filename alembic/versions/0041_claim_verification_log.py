"""Fabrication-proof claim engine audit (Feature A1).

CREATES
  claim_verification_log  one row per factual claim an AI-written outreach
                          message made about a prospect: verified (with the
                          stored evidence that supports it), stripped or
                          rewritten (with what could not be found)

Append-only by use; lead/message references are SET NULL on delete so the
record that a claim was refused outlives a GDPR erase of the prospect.

Revision ID: 0041_claim_verification_log
Revises: 0040_billing
"""

import sqlalchemy as sa
from alembic import op

revision = "0041_claim_verification_log"
down_revision = "0040_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claim_verification_log",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("field", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("extractor", sa.String(length=10), nullable=False),
        sa.Column("evidence_source", sa.String(length=300), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("unsupported_json", sa.JSON(), nullable=True),
        sa.Column("replacement_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_claim_verification_log"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_claim_verification_log_user_id_users"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="SET NULL",
                                name="fk_claim_verification_log_lead_id_leads"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL",
                                name="fk_claim_verification_log_message_id_messages"),
    )
    op.create_index("ix_claim_verification_log_user_id", "claim_verification_log",
                    ["user_id"])
    op.create_index("ix_claim_verification_log_message_id", "claim_verification_log",
                    ["message_id"])
    op.create_index("ix_claim_verification_log_lead_created", "claim_verification_log",
                    ["lead_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_claim_verification_log_lead_created",
                  table_name="claim_verification_log")
    op.drop_index("ix_claim_verification_log_message_id", table_name="claim_verification_log")
    op.drop_index("ix_claim_verification_log_user_id", table_name="claim_verification_log")
    op.drop_table("claim_verification_log")
