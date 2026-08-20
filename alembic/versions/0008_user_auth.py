"""user auth (M5)

- users.password_hash: PBKDF2 hash, nullable (pre-auth rows keep working
  until claimed via signup).

Revision ID: 0008_user_auth
Revises: 0007_multichannel_sequences
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008_user_auth'
down_revision: Union[str, None] = '0007_multichannel_sequences'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('password_hash', sa.String(length=300),
                                     nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'password_hash')
