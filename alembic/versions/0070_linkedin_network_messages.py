"""Messages the user writes to their own LinkedIn connections.

CREATES linkedin_network_messages: one row per (user, connection) holding the
text the user saved and its send status. Create-only. user_id and
connection_id are ON DELETE CASCADE, so erasing the network (or the account)
erases the messages.

Revision ID: 0070_linkedin_network_messages
Revises: 0069_user_full_name
"""

import sqlalchemy as sa
from alembic import op

revision = "0070_linkedin_network_messages"
down_revision = "0069_user_full_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "linkedin_network_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("connection_id", sa.Uuid(),
                  sa.ForeignKey("linkedin_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Uuid(),
                  sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(20), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "connection_id", name="uq_linkedin_msg_user_conn"),
    )
    op.create_index("ix_linkedin_network_messages_user_id", "linkedin_network_messages", ["user_id"])
    op.create_index("ix_linkedin_network_messages_connection_id",
                    "linkedin_network_messages", ["connection_id"])
    op.create_index("ix_linkedin_network_messages_product_id",
                    "linkedin_network_messages", ["product_id"])


def downgrade() -> None:
    op.drop_table("linkedin_network_messages")
