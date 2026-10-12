"""Voice twin -- "Your voice on calls" (AI calls in the owner's cloned voice,
AI answering of inbound calls, live takeover).

Spec: docs/features/voice-twin.md.

ADDS to calls (all server-defaulted or nullable; no existing row changes meaning):
  calls.direction         VARCHAR(10) NOT NULL DEFAULT 'outbound'
                          -- every existing call was an outbound call
  calls.voice_clone_used  BOOLEAN NOT NULL DEFAULT false
  calls.from_number       VARCHAR(40) NULL   -- inbound caller (E.164)
  calls.control_url       VARCHAR(500) NULL  -- provider live-control URL (secret)
CHANGES
  calls.lead_id           NOT NULL -> NULL   -- an inbound call from a number that
                                                is no lead of the account

CREATES
  voice_clones         one row per Professional Voice Clone of the account
                       owner's own voice: consent (version, exact text, typed
                       signature, time), provider voice id, status, counts.
                       NO audio column: recordings are never stored.
  voice_twin_settings  one row per account: use-my-voice / answer-inbound
                       switches, the provider number it answers on (UNIQUE),
                       the owner's transfer number, receptionist notes, pause.
  voice_clone_deletions  (review fix M3) provider voice ids whose delete failed
                       during an account erasure: provider, provider_voice_id,
                       attempts, last_error, timestamps. NO owner column and
                       nothing personal, so it survives the erasure and the
                       hourly task can finish deleting the voice model.

Constraint/index names follow app/db/base.py NAMING_CONVENTION and are all
well under PostgreSQL's 63-character limit (the longest is
uq_voice_twin_settings_inbound_phone_number_id, 46 characters).

DOWNGRADE drops both tables and the four columns, and makes calls.lead_id NOT
NULL again -- which first DELETES every call with no lead (inbound calls from
numbers that were not leads). That is lossy: export those calls first if they
matter. A clone that is still live at the provider is NOT deleted by a
downgrade; revoke every clone in the app (or delete it at ElevenLabs) BEFORE
downgrading, or its id is lost with the table. The same holds for any row
still in voice_clone_deletions: finish those deletes (or do them by hand at
ElevenLabs) before downgrading.

Revision ID: 0089_voice_twin
Revises: 0088_local_business
"""

import sqlalchemy as sa
from alembic import op

revision = "0089_voice_twin"
down_revision = "0088_local_business"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("calls") as batch:
        batch.add_column(sa.Column("direction", sa.String(10), nullable=False,
                                   server_default=sa.text("'outbound'")))
        batch.add_column(sa.Column("voice_clone_used", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("from_number", sa.String(40), nullable=True))
        batch.add_column(sa.Column("control_url", sa.String(500), nullable=True))
        batch.alter_column("lead_id", existing_type=sa.Uuid(), nullable=True)

    op.create_table(
        "voice_clones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False,
                  server_default=sa.text("'elevenlabs'")),
        sa.Column("provider_voice_id", sa.String(120), nullable=True),
        sa.Column("status", sa.String(30), nullable=False,
                  server_default=sa.text("'consented'")),
        sa.Column("consent_version", sa.String(10), nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column("consent_signature", sa.String(200), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sample_bytes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("provider_state_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_attempts", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_voice_clones_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_voice_clones"),
    )
    op.create_index("ix_voice_clones_user_id", "voice_clones", ["user_id"])

    op.create_table(
        "voice_twin_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("use_clone_for_calls", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("answer_inbound", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("inbound_phone_number_id", sa.String(120), nullable=True),
        sa.Column("transfer_number", sa.String(40), nullable=True),
        sa.Column("assistant_notes", sa.Text(), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_reason", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_voice_twin_settings_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_voice_twin_settings"),
        sa.UniqueConstraint("user_id", name="uq_voice_twin_settings_user_id"),
        sa.UniqueConstraint("inbound_phone_number_id",
                            name="uq_voice_twin_settings_inbound_phone_number_id"),
    )


    op.create_table(
        "voice_clone_deletions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_voice_id", sa.String(120), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_voice_clone_deletions"),
        sa.UniqueConstraint("provider", "provider_voice_id",
                            name="uq_voice_clone_deletions_provider_voice"),
    )


def downgrade() -> None:
    op.drop_table("voice_clone_deletions")
    op.drop_table("voice_twin_settings")
    op.drop_index("ix_voice_clones_user_id", table_name="voice_clones")
    op.drop_table("voice_clones")
    # Lossy, documented above: an inbound call with no lead cannot survive
    # lead_id becoming NOT NULL again.
    op.execute("DELETE FROM calls WHERE lead_id IS NULL")
    with op.batch_alter_table("calls") as batch:
        batch.alter_column("lead_id", existing_type=sa.Uuid(), nullable=False)
        batch.drop_column("control_url")
        batch.drop_column("from_number")
        batch.drop_column("voice_clone_used")
        batch.drop_column("direction")
