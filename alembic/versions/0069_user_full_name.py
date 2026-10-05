"""users.full_name: the display name a user sets on the Profile page.

ADDS one nullable column. Nothing is backfilled and no existing row changes.
Display only: not used for sending, identity or access.

Revision ID: 0069_user_full_name
Revises: 0068_linkedin_network
"""

import sqlalchemy as sa
from alembic import op

revision = "0069_user_full_name"
down_revision = "0068_linkedin_network"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "full_name")
