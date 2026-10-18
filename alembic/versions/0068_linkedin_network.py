"""Private LinkedIn network: imports, connections, per-product matches.

CREATES
  linkedin_imports              one row per uploaded export (counts only)
  linkedin_connections          one row per person, per uploading account
  linkedin_connection_matches   how relevant a connection is to one of that
                                account's own products

WHY NO SHARING. A connections export lists third parties who never agreed to be
shown to another Vectorae account. Every row carries the uploading user_id and
is only ever read back for that user. Email addresses and phone numbers in the
export are not stored at all -- there is no column for them.

user_id is ON DELETE CASCADE on all three tables, so deleting an account
deletes its network. Create-only: nothing existing is altered.

Revision ID: 0068_linkedin_network
Revises: 0067_strategy_steps_per_phase
"""

import sqlalchemy as sa
from alembic import op

revision = "0068_linkedin_network"
down_revision = "0067_strategy_steps_per_phase"
branch_labels = None
depends_on = None


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "linkedin_imports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("rows_in_file", sa.Integer(), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        *_ts(),
    )
    op.create_index("ix_linkedin_imports_user_id", "linkedin_imports", ["user_id"])

    op.create_table(
        "linkedin_connections",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("dedupe_key", sa.String(64), nullable=False),
        sa.Column("full_name", sa.String(300), nullable=False),
        sa.Column("company", sa.String(300), nullable=True),
        sa.Column("position", sa.String(300), nullable=True),
        sa.Column("profile_url", sa.String(500), nullable=True),
        sa.Column("connected_on", sa.Date(), nullable=True),
        *_ts(),
        sa.UniqueConstraint("user_id", "dedupe_key", name="uq_linkedin_conn_user_dedupe"),
    )
    op.create_index("ix_linkedin_connections_user_id", "linkedin_connections", ["user_id"])

    op.create_table(
        "linkedin_connection_matches",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("connection_id", sa.Uuid(),
                  sa.ForeignKey("linkedin_connections.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("product_id", sa.Uuid(),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("segment", sa.String(120), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        *_ts(),
        sa.UniqueConstraint("connection_id", "product_id",
                            name="uq_linkedin_match_conn_product"),
    )
    op.create_index("ix_linkedin_connection_matches_user_id",
                    "linkedin_connection_matches", ["user_id"])
    op.create_index("ix_linkedin_connection_matches_connection_id",
                    "linkedin_connection_matches", ["connection_id"])
    op.create_index("ix_linkedin_connection_matches_product_id",
                    "linkedin_connection_matches", ["product_id"])


def downgrade() -> None:
    op.drop_table("linkedin_connection_matches")
    op.drop_table("linkedin_connections")
    op.drop_table("linkedin_imports")
