"""Pre-send adversarial review of sequences (Feature A7).

CREATES
  sequence_reviews  one red-team pass over a sequence's content: findings,
                    status (passed | blocked | overridden), the content hash it
                    applies to, and -- for an override -- who, when and why

Revision ID: 0047_sequence_reviews
Revises: 0046_share_links
"""

import sqlalchemy as sa
from alembic import op

revision = "0047_sequence_reviews"
down_revision = "0046_share_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sequence_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sequence_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("findings_json", sa.JSON(), nullable=False),
        sa.Column("blocking_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("warning_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("reviewer", sa.String(length=20), nullable=False),
        sa.Column("overridden_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_sequence_reviews"),
        sa.ForeignKeyConstraint(["sequence_id"], ["sequences.id"], ondelete="CASCADE",
                                name="fk_sequence_reviews_sequence_id_sequences"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_sequence_reviews_user_id_users"),
        sa.ForeignKeyConstraint(["overridden_by_user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_sequence_reviews_overridden_by_user_id_users"),
    )
    op.create_index("ix_sequence_reviews_sequence_created", "sequence_reviews",
                    ["sequence_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_sequence_reviews_sequence_created", table_name="sequence_reviews")
    op.drop_table("sequence_reviews")
