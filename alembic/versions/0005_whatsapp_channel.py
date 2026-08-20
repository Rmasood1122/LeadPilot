"""whatsapp channel (M4 Chunk 1)

- leads: opt-in fields (compliance fact: status + when + how) and
  whatsapp_last_inbound_at (the 24h customer-service-window anchor,
  persisted by the webhook from Chunk 1, read by Chunk 3).
- whatsapp_templates: skeleton table; managed fully in Chunk 2.

Revision ID: 0005_whatsapp_channel
Revises: 0004_outreach_engine
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005_whatsapp_channel'
down_revision: Union[str, None] = '0004_outreach_engine'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('leads', sa.Column(
        'whatsapp_opted_in', sa.Boolean(), nullable=False,
        server_default=sa.false(),
    ))
    op.add_column('leads', sa.Column(
        'whatsapp_opt_in_at', sa.DateTime(timezone=True), nullable=True,
    ))
    op.add_column('leads', sa.Column(
        'whatsapp_opt_in_source', sa.String(length=100), nullable=True,
    ))
    op.add_column('leads', sa.Column(
        'whatsapp_last_inbound_at', sa.DateTime(timezone=True), nullable=True,
    ))

    op.create_table(
        'whatsapp_templates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('language', sa.String(length=20), nullable=False),
        sa.Column('status', sa.Enum(
            'draft', 'submitted', 'approved', 'rejected',
            name='whatsapptemplatestatus', native_enum=False, length=32,
        ), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('meta_template_id', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_whatsapp_templates')),
        sa.UniqueConstraint('name', 'language', name='template_name_language'),
    )
    op.create_index(op.f('ix_whatsapp_templates_name'),
                    'whatsapp_templates', ['name'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_whatsapp_templates_name'), table_name='whatsapp_templates')
    op.drop_table('whatsapp_templates')
    op.drop_column('leads', 'whatsapp_last_inbound_at')
    op.drop_column('leads', 'whatsapp_opt_in_source')
    op.drop_column('leads', 'whatsapp_opt_in_at')
    op.drop_column('leads', 'whatsapp_opted_in')
