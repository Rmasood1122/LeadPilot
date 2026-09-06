"""The calendar's business rules: availability -> offerable slots -> bookings.

Everything time-dependent takes an explicit `now`, exactly like
app/services/sequence_engine.py, so the slot generator is testable without
freezing the clock or waiting for a Tuesday.

WHY SLOTS ARE COMPUTED AND NOT STORED
The obvious alternative is a `calendar_slots` table materialised from the
availability rules. It loses immediately on two counts. Every edit to an
availability rule would have to regenerate a month of future rows and
reconcile them against bookings that already reference the old ones; and a
booking page's duration is a property of the PAGE, so the same Tuesday morning
is four 15-minute slots on one page and one 60-minute slot on another. There
is no single set of slots to store. Generating them per request is one pass
over at most 30 days x a handful of rules, and the result is always consistent
with the rules as they are right now.

THE THREE THINGS THAT MAKE A SLOT UNOFFERABLE
  1. it is in the past, or inside the minimum-notice window;
  2. it overlaps something already on the host's calendar;
  3. the page has hit its per-day booking cap for that date.

(2) is checked against the host's WHOLE calendar -- every live booking on any
of their pages, plus every meeting that is not cancelled -- not just the page
being viewed. A host with two booking pages is still one person: scoping the
conflict check to one page is how you get double-booked by your own website.

TIME ZONES
Availability rows carry wall-clock times plus the IANA zone they were written
in (see the model docstring for why they are not stored as UTC). This module
converts them to UTC per DAY, so a rule written in March is still 9am local in
November. Everything returned from here, and everything stored on a booking,
is an aware UTC datetime.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    BookingStatus,
    CalendarAvailability,
    CalendarBooking,
    CalendarBookingPage,
    Lead,
    Meeting,
    MeetingStatus,
    Product,
    Strategy,
    User,
)

__all__ = [
    "SLUG_PATTERN",
    "available_slots",
    "booking_page_by_slug",
    "normalize_slug",
    "owned_booking",
    "owned_booking_page",
    "resolve_timezone",
    "slot_key_for",
]

# Lowercase, digits and single hyphens. This string becomes a public URL path
# segment, so it is validated rather than escaped -- a slug that needs escaping
# to be safe in a URL is a slug that will be copied, pasted and broken.
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_LIVE_BOOKING_STATUSES = (BookingStatus.PENDING, BookingStatus.CONFIRMED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_timezone(name: str | None, fallback: str = "UTC") -> ZoneInfo:
    """A ZoneInfo for `name`, or the fallback zone if it is unusable.

    Never raises. The invitee's zone arrives from a browser and the host's
    from a form; neither is worth a 500, and an unknown zone degrading to UTC
    shows a time that is merely inconvenient rather than a page that does not
    load.
    """
    for candidate in (name, fallback, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return ZoneInfo("UTC")


def normalize_slug(raw: str) -> str:
    """Best-effort slugification, then validation by the caller.

    Deliberately does NOT silently repair anything it cannot: a title of
    "Intro Call" becomes "intro-call", but a slug the user typed that survives
    normalisation unchanged is the one that ends up in their URL.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", (raw or "").strip().lower()).strip("-")
    return slug


def slot_key_for(start_at: datetime) -> str:
    """The value that makes the double-booking UNIQUE constraint work.

    Second-resolution UTC. Not the raw isoformat: two clients can describe the
    same instant as "10:00:00+00:00" and "11:00:00+01:00", and a text key must
    map both to one string or the constraint compares strings that differ and
    lets both bookings in.
    """
    return start_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------
#
# Same semantics as app/services/crm_service.py::owned_lead: 404 rather than
# 403 for someone else's row, so existence cannot be probed by status code.


def owned_booking_page(db: Session, page_id: uuid.UUID,
                       current_user: User) -> CalendarBookingPage:
    page = db.get(CalendarBookingPage, page_id)
    if page is None or page.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="booking page not found")
    return page


def owned_booking(db: Session, booking_id: uuid.UUID,
                  current_user: User) -> CalendarBooking:
    booking = db.get(CalendarBooking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    page = db.get(CalendarBookingPage, booking.booking_page_id)
    if page is None or page.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="booking not found")
    return booking


def booking_page_by_slug(db: Session, slug: str) -> CalendarBookingPage:
    """The PUBLIC lookup. Inactive pages 404 like missing ones.

    An inactive page answering "this page is paused" would confirm the slug
    exists to anyone enumerating them, and there is no visitor for whom the
    distinction is actionable.
    """
    page = db.execute(
        select(CalendarBookingPage).where(
            CalendarBookingPage.slug == (slug or "").strip().lower(),
            CalendarBookingPage.is_active.is_(True),
        )
    ).scalars().first()
    if page is None:
        raise HTTPException(status_code=404, detail="booking page not found")
    return page


# ---------------------------------------------------------------------------
# Busy intervals
# ---------------------------------------------------------------------------


def busy_intervals(db: Session, user_id: uuid.UUID, window_start: datetime,
                   window_end: datetime) -> list[tuple[datetime, datetime]]:
    """Everything already on this host's calendar in the window, as UTC pairs.

    Two sources, deliberately: live bookings on ANY of the host's pages, and
    meetings that are not cancelled. Meetings are included because the manual
    path (Feature 3 creates a meeting from a proposed time with no booking
    behind it) would otherwise be invisible to the slot generator, and the
    host would be offered a slot they are already booked for. A meeting
    created FROM a booking double-counts the same interval, which costs
    nothing -- overlapping busy intervals block the same slots once.
    """
    pages = select(CalendarBookingPage.id).where(
        CalendarBookingPage.user_id == user_id
    )
    rows = db.execute(
        select(CalendarBooking.start_at, CalendarBooking.end_at).where(
            CalendarBooking.booking_page_id.in_(pages),
            CalendarBooking.status.in_(_LIVE_BOOKING_STATUSES),
            CalendarBooking.end_at > window_start,
            CalendarBooking.start_at < window_end,
        )
    ).all()
    rows += db.execute(
        select(Meeting.start_at, Meeting.end_at).where(
            Meeting.host_user_id == user_id,
            Meeting.status != MeetingStatus.CANCELLED,
            Meeting.end_at > window_start,
            Meeting.start_at < window_end,
        )
    ).all()
    return [(_as_utc(start), _as_utc(end)) for start, end in rows]


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes for timestamptz columns.

    PostgreSQL returns them aware, so without this the comparison operators
    below raise "can't compare offset-naive and offset-aware datetimes" on
    SQLite only -- i.e. the entire test suite -- while production is fine.
    Values are stored in UTC everywhere, so attaching UTC to a naive one is a
    restatement of what the column already means, not a conversion.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _overlaps(start: datetime, end: datetime,
              intervals: list[tuple[datetime, datetime]]) -> bool:
    return any(start < busy_end and end > busy_start
               for busy_start, busy_end in intervals)


# ---------------------------------------------------------------------------
# Slot generation
# ---------------------------------------------------------------------------


def available_slots(db: Session, page: CalendarBookingPage, *,
                    days: int | None = None,
                    now: datetime | None = None,
                    invitee_timezone: str | None = None) -> list[dict]:
    """Every bookable slot on `page` for the next `days` days.

    Returns [{"start_at": aware UTC datetime, "end_at": ..., "date": "YYYY-MM-DD"}]
    where `date` is the LOCAL date in the invitee's zone (falling back to the
    availability rule's zone). The date matters: a 23:30 slot in Karachi is the
    following day in UTC, and grouping the picker by UTC date would file it
    under a day the invitee did not click.
    """
    now = (now or _now()).astimezone(timezone.utc)
    days = days or settings.calendar_slot_days_ahead
    earliest = now + timedelta(minutes=settings.calendar_min_notice_minutes)

    rules = db.execute(
        select(CalendarAvailability).where(
            CalendarAvailability.user_id == page.user_id,
            CalendarAvailability.is_active.is_(True),
        )
    ).scalars().all()
    if not rules:
        return []

    window_end = now + timedelta(days=days + 1)
    busy = busy_intervals(db, page.user_id, now, window_end)
    per_day = _bookings_per_local_day(db, page, now, window_end)

    step = timedelta(minutes=page.duration_minutes + page.buffer_minutes)
    duration = timedelta(minutes=page.duration_minutes)
    display_tz = resolve_timezone(invitee_timezone, "UTC") if invitee_timezone else None

    slots: list[dict] = []
    seen: set[datetime] = set()
    for rule in rules:
        rule_tz = resolve_timezone(rule.timezone)
        # Iterate LOCAL dates in the rule's own zone. Iterating UTC dates and
        # converting would skip or duplicate a day for any host more than a
        # few hours off UTC.
        local_today = now.astimezone(rule_tz).date()
        for offset in range(days + 1):
            day = local_today + timedelta(days=offset)
            if day.weekday() != rule.day_of_week:
                continue

            cursor = _local(day, rule.start_time, rule_tz)
            window_close = _local(day, rule.end_time, rule_tz)
            if window_close <= cursor:
                # end_time <= start_time: an overnight window. Not supported,
                # and silently treating it as "all day" would be worse than
                # treating it as empty -- the user would be offered 3am.
                continue

            while cursor + duration <= window_close:
                start_at, end_at = cursor, cursor + duration
                cursor += step
                if start_at < earliest:
                    continue
                if start_at in seen:
                    # Overlapping rules for the same weekday would otherwise
                    # offer the same instant twice.
                    continue
                if _overlaps(start_at, end_at, busy):
                    continue
                local_date = start_at.astimezone(display_tz or rule_tz).date()
                if _day_is_full(page, per_day, local_date):
                    continue
                seen.add(start_at)
                slots.append({
                    "start_at": start_at,
                    "end_at": end_at,
                    "date": local_date.isoformat(),
                })

    slots.sort(key=lambda slot: slot["start_at"])
    return slots


def _local(day: date, at: time, tz: ZoneInfo) -> datetime:
    """A wall-clock time on a date in `tz`, as an aware UTC instant."""
    return datetime.combine(day, at.replace(tzinfo=None), tzinfo=tz).astimezone(
        timezone.utc
    )


def _bookings_per_local_day(db: Session, page: CalendarBookingPage,
                            window_start: datetime,
                            window_end: datetime) -> dict[str, int]:
    """Live bookings on THIS page, counted per local date.

    Per page, not per host: max_bookings_per_day is a property of the offer
    ("I will take at most three intro calls a day"), and counting a 60-minute
    deep dive against the intro-call budget would be a cap the user did not
    set.

    Counted in Python rather than with a SQL date_trunc because the grouping
    key is a local date under the page owner's zone, and the portable
    date-truncation branch this repo already carries
    (crm_service._date_bucket) only truncates in the database's zone.
    """
    counts: dict[str, int] = {}
    rows = db.execute(
        select(CalendarBooking.start_at).where(
            CalendarBooking.booking_page_id == page.id,
            CalendarBooking.status.in_(_LIVE_BOOKING_STATUSES),
            CalendarBooking.start_at >= window_start,
            CalendarBooking.start_at < window_end,
        )
    ).scalars().all()
    tz = _page_timezone(db, page)
    for start_at in rows:
        key = _as_utc(start_at).astimezone(tz).date().isoformat()
        counts[key] = counts.get(key, 0) + 1
    return counts


def _page_timezone(db: Session, page: CalendarBookingPage) -> ZoneInfo:
    """The host's zone, taken from their first active availability rule.

    There is no timezone column on the page or the user: the availability
    rules are the only place the host has told us what their day looks like,
    and inventing a second source would let the two disagree.
    """
    tz_name = db.execute(
        select(CalendarAvailability.timezone)
        .where(CalendarAvailability.user_id == page.user_id,
               CalendarAvailability.is_active.is_(True))
        .order_by(CalendarAvailability.day_of_week,
                  CalendarAvailability.start_time)
    ).scalars().first()
    return resolve_timezone(tz_name)


def _day_is_full(page: CalendarBookingPage, per_day: dict[str, int],
                 local_date: date) -> bool:
    if page.max_bookings_per_day is None:
        return False
    return per_day.get(local_date.isoformat(), 0) >= page.max_bookings_per_day


def slot_is_offered(db: Session, page: CalendarBookingPage, start_at: datetime,
                    now: datetime | None = None) -> bool:
    """Is `start_at` one of the slots this page is currently offering?

    The booking endpoint checks this before inserting. It is NOT the
    double-booking guard -- that is the UNIQUE (booking_page_id, slot_key)
    constraint, which is the only thing that survives two simultaneous
    requests. This check is what turns "you booked a time I never offered"
    (a hand-crafted POST, or a page left open past a change to the
    availability rules) into a 409 instead of a booking the host has to
    discover on their calendar.
    """
    target = start_at.astimezone(timezone.utc)
    return any(
        slot["start_at"] == target
        for slot in available_slots(db, page, now=now)
    )


# ---------------------------------------------------------------------------
# Lead linking
# ---------------------------------------------------------------------------


def match_lead_by_email(db: Session, user_id: uuid.UUID,
                        email: str | None) -> Lead | None:
    """The lead this invitee already is, if any -- scoped to the host.

    SCOPED TO THE HOST, deliberately and non-negotiably. The unscoped version
    of this query (`select(Lead).where(Lead.email == email)`) is the exact bug
    app/api/webhooks.py and app/workers/outreach_tasks.py were both fixed for:
    two customers prospecting the same person is routine in B2B, and matching
    globally attaches one tenant's booking to another tenant's lead, moves its
    status and stops their sequences.
    """
    address = (email or "").strip().lower()
    if not address:
        return None
    owned = (
        select(Lead.id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == user_id)
    )
    return db.execute(
        select(Lead)
        .where(Lead.id.in_(owned),
               or_(Lead.email == address, Lead.email == (email or "").strip()))
        .order_by(Lead.created_at.desc())
    ).scalars().first()
