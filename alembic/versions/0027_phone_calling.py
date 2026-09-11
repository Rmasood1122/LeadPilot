"""Feature Group 6 — AI phone calling.

CREATES
  calls   one AI outbound call: script, voicemail, recording, transcript,
          provider result and Claude's analysis

ALTERS (nullable -- existing leads read as "no consent recorded, never called")
  leads   phone_consent_at, phone_consent_source, last_call_at, last_call_outcome

ChannelType gains "phone"; it is a VARCHAR-backed enum, so no column changes.

WHY CONSENT IS A COLUMN AND NOT A FLAG IN SETTINGS
AI-voice calls and prerecorded voicemail drops to US numbers need the
person's prior express consent (TCPA; FCC ruling of February 2024 that AI
voices are "artificial"). Consent is a fact about a PERSON -- when, and how it
was obtained -- so it is recorded per lead, with its source, and the phone
channel checks it at call time.

Revision ID: 0027_phone_calling
Revises: 0026_linkedin_channel
"""

import sqlalchemy as sa
from alembic import op

revision = "0027_phone_calling"
down_revision = "0026_linkedin_channel"
branch_labels = None
depends_on = None

_LEAD_COLUMNS = [
    ("phone_consent_at", sa.DateTime(timezone=True)),
    ("phone_consent_source", sa.String(length=200)),
    ("last_call_at", sa.DateTime(timezone=True)),
    ("last_call_outcome", sa.String(length=30)),
]


def upgrade() -> None:
    op.create_table(
        "calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_call_id", sa.String(length=120), nullable=True),
        sa.Column("to_number", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("outcome",
                  sa.Enum("voicemail_dropped", "voicemail", "no_answer", "answered",
                          "interested", "not_interested", "failed",
                          name="calloutcome", native_enum=False, length=32),
                  nullable=True),
        sa.Column("script_json", sa.JSON(), nullable=True),
        sa.Column("voicemail_text", sa.Text(), nullable=True),
        sa.Column("voicemail_audio_url", sa.String(length=500), nullable=True),
        sa.Column("recording_url", sa.String(length=1000), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("ended_reason", sa.String(length=80), nullable=True),
        sa.Column("analysis_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_calls"),
        sa.UniqueConstraint("provider", "provider_call_id", name="call_provider_id"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE",
                                name="fk_calls_lead_id_leads"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL",
                                name="fk_calls_strategy_id_strategies"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name="fk_calls_user_id_users"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL",
                                name="fk_calls_message_id_messages"),
    )
    op.create_index("ix_calls_lead_id", "calls", ["lead_id"])
    op.create_index("ix_calls_outcome", "calls", ["outcome"])
    op.create_index("ix_calls_strategy_created", "calls", ["strategy_id", "created_at"])

    for name, type_ in _LEAD_COLUMNS:
        op.add_column("leads", sa.Column(name, type_, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("leads") as batch:
        for name, _ in reversed(_LEAD_COLUMNS):
            batch.drop_column(name)
    op.drop_table("calls")
