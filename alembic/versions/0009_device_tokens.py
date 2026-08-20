"""device_tokens table for FCM push notifications (M7 Chunk 3)

Revision ID: 0009_device_tokens
Revises: 0008_user_auth
Create Date: 2026-08-16

INTEGRATION REPAIR NOTE (combined build): the version of this migration
shipped in the M7 zip used Integer id/user_id columns and an
`ALTER TYPE outcomeevent` statement. Both were written against M7's
simplified model file and could never apply on the real M1–M5 schema
(users.id is UUID; all enums are VARCHAR-backed with native_enum=False),
so the file is repaired here rather than patched with a follow-up —
it has never successfully run in any environment.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009_device_tokens'
down_revision: Union[str, None] = '0008_user_auth'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'device_tokens',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('token', sa.String(512), nullable=False),
        sa.Column('platform', sa.String(20), nullable=False, server_default='android'),
        sa.Column('is_valid', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'token', name='uq_device_tokens_user_token'),
    )
    op.create_index('ix_device_tokens_user_id', 'device_tokens', ['user_id'])
    # No ALTER TYPE needed: OutcomeEvent is VARCHAR-backed (native_enum=False),
    # so new enum members ('notification_sent') are a code-only change.


def downgrade() -> None:
    op.drop_index('ix_device_tokens_user_id', table_name='device_tokens')
    op.drop_table('device_tokens')
