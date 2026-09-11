"""Feature expansion foundation + Feature Group 7 (meeting preparation).

WHAT THIS ADDS
Four tables, additive, and one relaxed constraint:

  system_settings       admin-controlled deployment-wide feature settings
                        (app/services/system_settings.py owns the keys)
  deals                 revenue linked to a lead and a campaign (strategy)
  meeting_prep_briefs   the brief generated when a meeting is booked; also
                        the at-most-once ledger for the 24h / 1h reminders
  meeting_outcomes      "Log Meeting Outcome" submissions + the follow-up
                        email draft each one produced

  integration_tokens.user_id  NOT NULL -> NULL. A NULL owner is the SYSTEM
                        scope: deployment-wide credentials (the OpenAI key for
                        the consensus engine, the Slack app's client secret)
                        that an admin sets in the panel instead of an env var.
                        See app/services/credentials.py.

WHY deals STORES INTEGER CENTS
A Float cannot hold 0.10 exactly and the revenue dashboard sums these across
campaigns. Numeric works on PostgreSQL but comes back from SQLite as a float,
and the test suite runs on SQLite. BIGINT cents are exact on both.

WHY meeting_prep_briefs IS UNIQUE ON (lead_id, source, external_ref)
external_ref is the Calendly event URI or our own booking id, so a Calendly
retry -- or one booking reaching both the webhook path and the calendar path --
updates one brief instead of producing two, and two sets of reminders.

integration_tokens IS ALTERED IN BATCH MODE because SQLite cannot ALTER a
column's nullability in place; on PostgreSQL batch mode is a plain ALTER.

DOWNGRADE
Drops the four tables (every brief, outcome and deal is destroyed -- take a
dump first) and deletes system-scope credentials before restoring NOT NULL,
because the constraint cannot be restored over rows that violate it.

Revision ID: 0023_meeting_prep
Revises: 0022_meetings
"""

import sqlalchemy as sa
from alembic import op

revision = "0023_meeting_prep"
down_revision = "0022_meetings"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    """created_at/updated_at exactly as TimestampMixin declares them."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    # ---- system_settings -------------------------------------------------
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_system_settings"),
        sa.UniqueConstraint("key", name="system_setting_key"),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"], ["users.id"], ondelete="SET NULL",
            name="fk_system_settings_updated_by_user_id_users"),
    )

    # ---- deals -------------------------------------------------------------
    op.create_table(
        "deals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("value_cents", sa.BigInteger(), server_default=sa.text("0"),
                  nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD",
                  nullable=False),
        sa.Column("stage",
                  sa.Enum("open", "won", "lost", name="dealstage",
                          native_enum=False, length=32),
                  nullable=False),
        sa.Column("close_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=30), server_default="manual",
                  nullable=False),
        sa.Column("external_ref", sa.String(length=200), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_deals"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_deals_user_id_users"),
        # SET NULL on both: a GDPR-deleted lead or a deleted strategy must
        # not erase revenue that was really earned.
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="SET NULL",
            name="fk_deals_lead_id_leads"),
        sa.ForeignKeyConstraint(
            ["strategy_id"], ["strategies.id"], ondelete="SET NULL",
            name="fk_deals_strategy_id_strategies"),
    )
    op.create_index("ix_deals_user_id", "deals", ["user_id"])
    op.create_index("ix_deals_lead_id", "deals", ["lead_id"])
    op.create_index("ix_deals_strategy_id", "deals", ["strategy_id"])
    op.create_index("ix_deals_stage", "deals", ["stage"])
    op.create_index("ix_deals_user_close", "deals", ["user_id", "close_date"])

    # ---- meeting_prep_briefs ---------------------------------------------
    op.create_table(
        "meeting_prep_briefs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=True),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("external_ref", sa.String(length=200), nullable=True),
        sa.Column("meeting_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meeting_url", sa.String(length=1000), nullable=True),
        sa.Column("status",
                  sa.Enum("pending", "generating", "ready", "failed",
                          name="meetingprepstatus", native_enum=False,
                          length=32),
                  nullable=False),
        sa.Column("content_md", sa.Text(), nullable=True),
        sa.Column("sections_json", sa.JSON(), nullable=True),
        sa.Column("profile_json", sa.JSON(), nullable=True),
        sa.Column("opening_script", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_24h_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminder_1h_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_meeting_prep_briefs"),
        sa.UniqueConstraint("lead_id", "source", "external_ref",
                            name="meeting_prep_brief_source_ref"),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="CASCADE",
            name="fk_meeting_prep_briefs_lead_id_leads"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_meeting_prep_briefs_user_id_users"),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meetings.id"], ondelete="SET NULL",
            name="fk_meeting_prep_briefs_meeting_id_meetings"),
        sa.ForeignKeyConstraint(
            ["booking_id"], ["calendar_bookings.id"], ondelete="SET NULL",
            name="fk_meeting_prep_briefs_booking_id_calendar_bookings"),
    )
    op.create_index("ix_meeting_prep_briefs_lead_id", "meeting_prep_briefs",
                    ["lead_id"])
    op.create_index("ix_meeting_prep_briefs_user_id", "meeting_prep_briefs",
                    ["user_id"])
    op.create_index("ix_meeting_prep_briefs_status", "meeting_prep_briefs",
                    ["status"])
    # The reminder sweep's query: briefs whose meeting starts in the next 24h.
    op.create_index("ix_meeting_prep_briefs_start", "meeting_prep_briefs",
                    ["meeting_start_at"])

    # ---- meeting_outcomes ------------------------------------------------
    op.create_table(
        "meeting_outcomes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("meeting_id", sa.Uuid(), nullable=True),
        sa.Column("brief_id", sa.Uuid(), nullable=True),
        sa.Column("deal_id", sa.Uuid(), nullable=True),
        sa.Column("outcome",
                  sa.Enum("interested", "needs_follow_up", "not_a_fit",
                          "closed_won", "closed_lost",
                          name="meetingoutcomekind", native_enum=False,
                          length=32),
                  nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=True),
        sa.Column("followup_subject", sa.String(length=500), nullable=True),
        sa.Column("followup_body", sa.Text(), nullable=True),
        sa.Column("draft_status", sa.String(length=30), server_default="pending",
                  nullable=False),
        sa.Column("draft_error", sa.Text(), nullable=True),
        sa.Column("gmail_draft_id", sa.String(length=128), nullable=True),
        sa.Column("gmail_message_id", sa.String(length=128), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_meeting_outcomes"),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="CASCADE",
            name="fk_meeting_outcomes_lead_id_leads"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="SET NULL",
            name="fk_meeting_outcomes_user_id_users"),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meetings.id"], ondelete="SET NULL",
            name="fk_meeting_outcomes_meeting_id_meetings"),
        sa.ForeignKeyConstraint(
            ["brief_id"], ["meeting_prep_briefs.id"], ondelete="SET NULL",
            name="fk_meeting_outcomes_brief_id_meeting_prep_briefs"),
        sa.ForeignKeyConstraint(
            ["deal_id"], ["deals.id"], ondelete="SET NULL",
            name="fk_meeting_outcomes_deal_id_deals"),
    )
    op.create_index("ix_meeting_outcomes_lead_id", "meeting_outcomes",
                    ["lead_id"])

    # ---- integration_tokens: allow the system scope ------------------------
    with op.batch_alter_table("integration_tokens") as batch:
        batch.alter_column("user_id", existing_type=sa.Uuid(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM integration_tokens WHERE user_id IS NULL")
    with op.batch_alter_table("integration_tokens") as batch:
        batch.alter_column("user_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_table("meeting_outcomes")
    op.drop_table("meeting_prep_briefs")
    op.drop_table("deals")
    op.drop_table("system_settings")
