"""multichannel sequences (M4 Chunk 3)

- sequence_steps: per-step channel override + WhatsApp fields (kind,
  template ref, variable mapping). NULL channel = sequence's channel, so
  every M3 sequence keeps working unchanged.
- messages: whatsapp_kind + whatsapp_template_id snapshot.
- outcomes: real `channel` column (backfilled 'email' — every pre-M4
  outcome was email) so M8 can compare channel performance with plain SQL.
- inbound_replies: `channel` column, same backfill reasoning.

Revision ID: 0007_multichannel_sequences
Revises: 0006_whatsapp_templates_optins
Create Date: 2026-08-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007_multichannel_sequences'
down_revision: Union[str, None] = '0006_whatsapp_templates_optins'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_channeltype = sa.Enum('email', 'whatsapp', 'linkedin',
                       name='channeltype', native_enum=False, length=32)
_stepkind = sa.Enum('template', 'text',
                    name='whatsappstepkind', native_enum=False, length=32)


def upgrade() -> None:
    with op.batch_alter_table('sequence_steps') as batch:
        batch.add_column(sa.Column('channel', _channeltype, nullable=True))
        batch.add_column(sa.Column('whatsapp_kind', _stepkind, nullable=True))
        batch.add_column(sa.Column('whatsapp_template_id', sa.Uuid(), nullable=True))
        batch.add_column(sa.Column('variable_mapping_json', sa.JSON(), nullable=True))
        batch.create_foreign_key(
            op.f('fk_sequence_steps_whatsapp_template_id_whatsapp_templates'),
            'whatsapp_templates', ['whatsapp_template_id'], ['id'],
            ondelete='SET NULL',
        )

    with op.batch_alter_table('messages') as batch:
        batch.add_column(sa.Column('whatsapp_kind', _stepkind, nullable=True))
        batch.add_column(sa.Column('whatsapp_template_id', sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            op.f('fk_messages_whatsapp_template_id_whatsapp_templates'),
            'whatsapp_templates', ['whatsapp_template_id'], ['id'],
            ondelete='SET NULL',
        )

    # Backfill 'email': every outcome/inbound before M4 was on email.
    op.add_column('outcomes', sa.Column('channel', sa.String(length=20),
                                        nullable=False, server_default='email'))
    op.create_index(op.f('ix_outcomes_channel'), 'outcomes', ['channel'])
    op.add_column('inbound_replies', sa.Column('channel', sa.String(length=20),
                                               nullable=False,
                                               server_default='email'))
    op.create_index(op.f('ix_inbound_replies_channel'),
                    'inbound_replies', ['channel'])


def downgrade() -> None:
    op.drop_index(op.f('ix_inbound_replies_channel'), table_name='inbound_replies')
    op.drop_column('inbound_replies', 'channel')
    op.drop_index(op.f('ix_outcomes_channel'), table_name='outcomes')
    op.drop_column('outcomes', 'channel')
    with op.batch_alter_table('messages') as batch:
        batch.drop_constraint(
            op.f('fk_messages_whatsapp_template_id_whatsapp_templates'),
            type_='foreignkey')
        batch.drop_column('whatsapp_template_id')
        batch.drop_column('whatsapp_kind')
    with op.batch_alter_table('sequence_steps') as batch:
        batch.drop_constraint(
            op.f('fk_sequence_steps_whatsapp_template_id_whatsapp_templates'),
            type_='foreignkey')
        batch.drop_column('variable_mapping_json')
        batch.drop_column('whatsapp_template_id')
        batch.drop_column('whatsapp_kind')
        batch.drop_column('channel')
