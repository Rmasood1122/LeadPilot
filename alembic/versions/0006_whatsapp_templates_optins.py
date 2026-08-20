"""whatsapp templates + optins (M4 Chunk 2)

- whatsapp_templates: category, variable descriptions, rejection reason,
  versioning (unique constraint moves from (name, language) to
  (name, language, version)) and supersedes_id for immutable-approved
  edit flow.
- whatsapp_optins: APPEND-ONLY consent audit trail (status, source,
  evidence, consent text). The lead's boolean fields from 0005 become a
  denormalized cache of the latest row here.

Revision ID: 0006_whatsapp_templates_optins
Revises: 0005_whatsapp_channel
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006_whatsapp_templates_optins'
down_revision: Union[str, None] = '0005_whatsapp_channel'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- whatsapp_templates lifecycle fields -----------------------------
    # batch_alter_table so the constraint swap also works on SQLite (tests).
    with op.batch_alter_table('whatsapp_templates') as batch:
        batch.add_column(sa.Column('version', sa.Integer(), nullable=False,
                                   server_default='1'))
        batch.add_column(sa.Column('category', sa.Enum(
            'marketing', 'utility',
            name='whatsapptemplatecategory', native_enum=False, length=32,
        ), nullable=False, server_default='marketing'))
        batch.add_column(sa.Column('variable_descriptions_json', sa.JSON(),
                                   nullable=True))
        batch.add_column(sa.Column('rejection_reason', sa.Text(), nullable=True))
        batch.add_column(sa.Column('supersedes_id', sa.Uuid(), nullable=True))
        batch.drop_constraint('template_name_language', type_='unique')
        batch.create_unique_constraint(
            'template_name_language_version', ['name', 'language', 'version']
        )
        batch.create_foreign_key(
            op.f('fk_whatsapp_templates_supersedes_id_whatsapp_templates'),
            'whatsapp_templates', ['supersedes_id'], ['id'],
            ondelete='SET NULL',
        )

    # --- whatsapp_optins ---------------------------------------------------
    op.create_table(
        'whatsapp_optins',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('lead_id', sa.Uuid(), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('status', sa.Enum(
            'opted_in', 'opted_out', 'unknown',
            name='optinstatus', native_enum=False, length=32,
        ), nullable=False),
        sa.Column('source', sa.Enum(
            'web_form', 'inbound_message', 'manual_import', 'api',
            name='optinsource', native_enum=False, length=32,
        ), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=True),
        sa.Column('consent_text', sa.Text(), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['lead_id'], ['leads.id'],
            name=op.f('fk_whatsapp_optins_lead_id_leads'), ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_whatsapp_optins')),
    )
    op.create_index(op.f('ix_whatsapp_optins_lead_id'),
                    'whatsapp_optins', ['lead_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_whatsapp_optins_lead_id'), table_name='whatsapp_optins')
    op.drop_table('whatsapp_optins')
    with op.batch_alter_table('whatsapp_templates') as batch:
        batch.drop_constraint(
            op.f('fk_whatsapp_templates_supersedes_id_whatsapp_templates'),
            type_='foreignkey',
        )
        batch.drop_constraint('template_name_language_version', type_='unique')
        batch.create_unique_constraint('template_name_language', ['name', 'language'])
        batch.drop_column('supersedes_id')
        batch.drop_column('rejection_reason')
        batch.drop_column('variable_descriptions_json')
        batch.drop_column('category')
        batch.drop_column('version')
