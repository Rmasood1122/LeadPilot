"""Engagement Hub, Feature 3 — meetings, notes, transcripts and AI summaries.

WHAT THIS ADDS
Two new tables, additive:

  meetings              one call: platform, join URL, notes, transcript,
                        AI summary, action items
  meeting_participants  who was on it, and when they joined and left

WHY meetings.booking_id IS NULLABLE
Not every meeting comes from a booking page. The prospect proposes a time over
email, or the call was on the books before this feature shipped. A NOT NULL
booking_id would make the manual path impossible and force placeholder
bookings to be written purely to satisfy the schema -- rows that would then
appear on the user's calendar as bookings nobody made.

WHY meetings CARRIES ITS OWN lead_id
It duplicates calendar_bookings.lead_id for meetings that came from a booking,
and that is deliberate. Feature 4's "Meetings" tab on a lead is a single
indexed lookup here; without it, the same query is a LEFT JOIN through
calendar_bookings that resolves only the booked half of the rows and silently
omits every manually created meeting for that lead.

WHY THERE ARE FIVE AI COLUMNS AND NOT ONE
app/services/meeting_ai.py returns {summary, key_points, action_items,
next_steps, sentiment}. Collapsing the structured four into ai_notes prose
would mean the UI re-parsing them out of free text on every render to draw a
bullet list, a checkbox list and a sentiment chip -- and a summary panel that
re-parses is a summary panel that eventually renders something the model did
not say. action_items/key_points/next_steps are JSON; sentiment is a short
VARCHAR; ai_notes keeps the model's narrative form for anyone who wants to
read it as written.

raw_notes IS NEVER WRITTEN BY THE MODEL. It is what the human typed during the
call, and it is a separate column from ai_notes precisely so that generating
(or regenerating) a summary cannot overwrite it.

THE TWO TIME PAIRS ARE DIFFERENT FACTS
start_at/end_at are what was scheduled. actual_start_at/actual_end_at are when
Start Meeting and End Meeting were pressed. The summary prompt uses the actual
duration: "booked 60 minutes, ran 12" is a signal about how the call went, and
storing only one pair would erase it.

DOWNGRADE
Drops both tables. Every transcript, note and summary is destroyed and exists
nowhere else -- recordings live at recording_url, on the provider, but the
notes and the AI output do not. Take a dump first.

Revision ID: 0022_meetings
Revises: 0021_calendar
"""

import sqlalchemy as sa
from alembic import op

revision = "0022_meetings"
down_revision = "0021_calendar"
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
    # ---- meetings --------------------------------------------------------
    op.create_table(
        "meetings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column("host_user_id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("platform",
                  sa.Enum("google_meet", "zoom", "teams", "custom",
                          name="meetingplatform", native_enum=False, length=32),
                  nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("meeting_url", sa.String(length=1000), nullable=True),
        sa.Column("external_event_id", sa.String(length=200), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actual_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status",
                  sa.Enum("scheduled", "in_progress", "completed", "cancelled",
                          name="meetingstatus", native_enum=False, length=32),
                  nullable=False),
        sa.Column("raw_notes", sa.Text(), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("recording_url", sa.Text(), nullable=True),
        sa.Column("ai_notes", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("action_items", sa.JSON(), nullable=True),
        sa.Column("key_points", sa.JSON(), nullable=True),
        sa.Column("next_steps", sa.JSON(), nullable=True),
        sa.Column("sentiment", sa.String(length=20), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_meetings"),
        # SET NULL on both optional links: deleting a booking or a lead must
        # not take the record of the call (and its transcript) with it.
        sa.ForeignKeyConstraint(
            ["booking_id"], ["calendar_bookings.id"], ondelete="SET NULL",
            name="fk_meetings_booking_id_calendar_bookings"),
        sa.ForeignKeyConstraint(
            ["host_user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_meetings_host_user_id_users"),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="SET NULL",
            name="fk_meetings_lead_id_leads"),
    )
    op.create_index("ix_meetings_booking_id", "meetings", ["booking_id"])
    op.create_index("ix_meetings_host_user_id", "meetings", ["host_user_id"])
    op.create_index("ix_meetings_lead_id", "meetings", ["lead_id"])
    op.create_index("ix_meetings_start_at", "meetings", ["start_at"])
    op.create_index("ix_meetings_status", "meetings", ["status"])
    # The list endpoint's query: this user's meetings, newest (or soonest)
    # first, over a date range.
    op.create_index("ix_meetings_host_start", "meetings",
                    ["host_user_id", "start_at"])

    # ---- meeting_participants -------------------------------------------
    op.create_table(
        "meeting_participants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("meeting_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("role",
                  sa.Enum("host", "client", "observer",
                          name="meetingparticipantrole", native_enum=False,
                          length=32),
                  nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_meeting_participants"),
        sa.ForeignKeyConstraint(
            ["meeting_id"], ["meetings.id"], ondelete="CASCADE",
            name="fk_meeting_participants_meeting_id_meetings"),
    )
    op.create_index("ix_meeting_participants_meeting_id",
                    "meeting_participants", ["meeting_id"])


def downgrade() -> None:
    op.drop_table("meeting_participants")
    op.drop_table("meetings")
