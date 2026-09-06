"""Engagement Hub, Feature 2 — the self-built calendar.

WHAT THIS ADDS
Three new tables, all additive. No existing table is touched.

  calendar_availability   recurring weekly windows a user is bookable in
  calendar_booking_pages  a shareable /book/<slug> offer over that availability
  calendar_bookings       one booked slot, optionally linked to a lead

WHY NOT JUST USE CALENDLY
app/integrations/calendly.py is untouched and keeps working for accounts that
already run on it. The difference is where a booking LANDS. A Calendly booking
arrives as one webhook for the whole deployment, carrying the invitee's email
and no account identity, which is why calendly.py has to smuggle the tenant id
through a utm_content parameter and treat "we cannot tell" as "do not match"
(see its tenant-tagging note). A booking made against a page in this schema
already knows its page, and the page already knows its owner -- so ownership
is a foreign key rather than an inference, and cross-tenant mismatching is not
a failure mode that exists.

THE COLUMN THE BRIEF DOES NOT LIST: calendar_bookings.slot_key
Two invitees can submit the same 10:00 slot in the same second. A
check-then-insert in the request handler loses that race and double-books.
The obvious fix -- a partial unique index, `UNIQUE (booking_page_id, start_at)
WHERE status <> 'cancelled'` -- is PostgreSQL-only, so the SQLite test suite
would be exercising a constraint production does not have and vice versa.

slot_key instead holds the slot's UTC start while the booking is live, and is
set to NULL when it is cancelled. NULLs never collide in a UNIQUE constraint
on either dialect, so `UNIQUE (booking_page_id, slot_key)` blocks a second
live booking of the same slot on both, and a cancelled slot becomes bookable
again the moment it is released. One insert, no read, no race, one behaviour
in tests and in production.

TIMES AND TIME ZONES
calendar_availability stores WALL-CLOCK times plus the IANA zone they are
written in, not UTC. "I take calls at 9am" is a fact about the user's morning;
stored as UTC it would drift by an hour twice a year and start offering 8am or
10am slots on its own. Conversion happens per offered day in
app/services/calendar_service.py, so DST is resolved against the date being
booked. calendar_bookings.start_at/end_at are timestamptz -- an instant, which
is what a booking actually is -- with the invitee's own zone kept alongside so
the confirmation email can render the time they chose it in.

DOWNGRADE
Drops all three tables. Every booking, every booking page and every
availability rule is destroyed and exists nowhere else. Take a dump first.

Revision ID: 0021_calendar
Revises: 0020_followup_delay
"""

import sqlalchemy as sa
from alembic import op

revision = "0021_calendar"
down_revision = "0020_followup_delay"
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
    # ---- calendar_availability ------------------------------------------
    op.create_table(
        "calendar_availability",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        # 0 = Monday .. 6 = Sunday, i.e. datetime.weekday(). Pinned by a CHECK
        # so a client sending 7 (a Sunday under the other common convention)
        # fails at the database rather than creating a rule that can never
        # match a day.
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False,
                  server_default="UTC"),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_calendar_availability"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_calendar_availability_user_id_users"),
        sa.CheckConstraint("day_of_week >= 0 AND day_of_week <= 6",
                           name="ck_calendar_availability_calendar_availability_dow"),
    )
    op.create_index("ix_calendar_availability_user_id",
                    "calendar_availability", ["user_id"])

    # ---- calendar_booking_pages -----------------------------------------
    op.create_table(
        "calendar_booking_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False,
                  server_default=sa.text("30")),
        sa.Column("buffer_minutes", sa.Integer(), nullable=False,
                  server_default=sa.text("0")),
        # NULL = unlimited. 0 would read as "nobody may book", which is the
        # opposite of what an unset field should mean.
        sa.Column("max_bookings_per_day", sa.Integer(), nullable=True),
        sa.Column("custom_questions", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_calendar_booking_pages"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE",
            name="fk_calendar_booking_pages_user_id_users"),
        # Global, not per-user: the slug IS the public URL, so two accounts
        # cannot both own /book/intro-call.
        sa.UniqueConstraint("slug", name="calendar_booking_page_slug"),
        sa.CheckConstraint(
            "duration_minutes IN (15, 30, 45, 60)",
            name="ck_calendar_booking_pages_calendar_booking_page_duration"),
    )
    op.create_index("ix_calendar_booking_pages_user_id",
                    "calendar_booking_pages", ["user_id"])
    op.create_index("ix_calendar_booking_pages_slug",
                    "calendar_booking_pages", ["slug"])

    # ---- calendar_bookings ----------------------------------------------
    op.create_table(
        "calendar_bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_page_id", sa.Uuid(), nullable=False),
        sa.Column("invitee_name", sa.String(length=200), nullable=False),
        sa.Column("invitee_email", sa.String(length=320), nullable=False),
        sa.Column("invitee_phone", sa.String(length=50), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invitee_timezone", sa.String(length=64), nullable=True),
        sa.Column("meeting_link", sa.String(length=500), nullable=True),
        # VARCHAR-backed enum, native_enum=False, exactly like every other
        # enum column in this schema: adding a status later is a data-free
        # change and SQLite behaves identically to PostgreSQL.
        sa.Column("status",
                  sa.Enum("pending", "confirmed", "cancelled", "no_show",
                          name="bookingstatus", native_enum=False, length=32),
                  nullable=False),
        # SET NULL, not CASCADE: deleting a lead must not erase the fact that
        # a meeting was booked.
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("answers", sa.JSON(), nullable=True),
        # The double-booking guard. See the module docstring.
        sa.Column("slot_key", sa.String(length=40), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_calendar_bookings"),
        sa.ForeignKeyConstraint(
            ["booking_page_id"], ["calendar_booking_pages.id"],
            ondelete="CASCADE",
            name="fk_calendar_bookings_booking_page_id_calendar_booking_pages"),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], ondelete="SET NULL",
            name="fk_calendar_bookings_lead_id_leads"),
        sa.UniqueConstraint("booking_page_id", "slot_key",
                            name="calendar_booking_live_slot"),
    )
    op.create_index("ix_calendar_bookings_booking_page_id",
                    "calendar_bookings", ["booking_page_id"])
    op.create_index("ix_calendar_bookings_invitee_email",
                    "calendar_bookings", ["invitee_email"])
    op.create_index("ix_calendar_bookings_start_at",
                    "calendar_bookings", ["start_at"])
    op.create_index("ix_calendar_bookings_status",
                    "calendar_bookings", ["status"])
    op.create_index("ix_calendar_bookings_lead_id",
                    "calendar_bookings", ["lead_id"])
    # The "what is on my calendar between these dates" query, which is every
    # read the week grid and the slots endpoint make.
    op.create_index("ix_calendar_bookings_page_start",
                    "calendar_bookings", ["booking_page_id", "start_at"])


def downgrade() -> None:
    # Reverse creation order: calendar_bookings references calendar_booking_pages.
    op.drop_table("calendar_bookings")
    op.drop_table("calendar_booking_pages")
    op.drop_table("calendar_availability")
