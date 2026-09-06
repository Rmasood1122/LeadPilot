"""Engagement Hub, Feature 2 — the calendar API.

CONVENTIONS THIS ROUTER FOLLOWS (none of them invented here)

  auth        `Depends(get_current_user)` on every route EXCEPT the two
              public ones the booking page needs: GET .../slots and
              POST .../book. Those are the only unauthenticated routes in
              this file and both are marked, because "which endpoints does a
              stranger reach?" must be answerable by reading, not by auditing.
  ownership   app/services/calendar_service.py::owned_booking_page /
              owned_booking, which answer 404 (never 403) for another
              account's row -- the same rule app/api/crm.py and
              app/api/leads.py follow, so a probe cannot distinguish "not
              yours" from "does not exist".
  rate limit  `enforce_rate_limit(...)` as the handler's FIRST statement, not
              a route dependency. app/core/rate_limiting.py documents why at
              length, and tests/test_rate_limit_ordering.py pins it: as a
              dependency it runs before FastAPI validates the body, so a
              typo'd payload burns a slot having created nothing.

WHY THE PUBLIC BOOKING ENDPOINT IS SAFE TO EXPOSE
It can create exactly one kind of row, on a page whose owner chose to publish
it, in a slot that page is currently offering, with a UNIQUE constraint
standing behind the availability check. It reads no lead data back to the
caller: the auto-link to a Lead happens server-side and nothing about it
appears in the response, so a stranger cannot use it to test whether an
address is in somebody's CRM.
"""

# NOTE: deliberately NO `from __future__ import annotations`, matching every
# other router in this package. With postponed evaluation FastAPI resolves a
# `-> None` return annotation to the NoneType class, which is truthy, and every
# 204 route in the file then fails at import with "Status code 204 must not
# have a response body".

import uuid
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.logging import get_logger
from app.core.rate_limiting import client_ip, enforce_rate_limit
from app.db.base import get_db
from app.db.models import (
    BookingStatus,
    CalendarAvailability,
    CalendarBooking,
    CalendarBookingPage,
    User,
)
from app.services import calendar_service as cal

logger = get_logger("api.calendar")

router = APIRouter(prefix="/calendar", tags=["calendar"])

_WRITE_LIMIT = "RATE_LIMIT_CALENDAR_WRITE"
_PUBLIC_LIMIT = "RATE_LIMIT_PUBLIC_BOOKING"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AvailabilityIn(BaseModel):
    day_of_week: int = Field(ge=0, le=6, description="0 = Monday .. 6 = Sunday")
    start_time: time
    end_time: time
    timezone: str = Field(default="UTC", max_length=64)
    is_active: bool = True

    @field_validator("end_time")
    @classmethod
    def _end_after_start(cls, value: time, info):
        start = info.data.get("start_time")
        if start is not None and value <= start:
            # Rejected rather than interpreted as an overnight window: the
            # slot generator would silently produce nothing for such a rule,
            # and a rule that generates no slots while looking correct in the
            # UI is worse than a validation error.
            raise ValueError("end_time must be after start_time")
        return value

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown IANA time zone: {value!r}") from None
        return value


class AvailabilityOut(AvailabilityIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class AvailabilityReplaceIn(BaseModel):
    """The WHOLE weekly schedule, replacing what is there.

    PUT with the complete set rather than per-row POST/PATCH/DELETE, because
    the thing the user edits is a week, not a list of rows: they drag a block,
    delete one, add another, and press Save. Reconciling that into three kinds
    of request means the client can leave the server in a state the user never
    saw if one of them fails.
    """

    blocks: list[AvailabilityIn] = Field(default_factory=list, max_length=100)


class BookingPageIn(BaseModel):
    slug: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    duration_minutes: int = 30
    buffer_minutes: int = Field(default=0, ge=0, le=120)
    max_bookings_per_day: int | None = Field(default=None, ge=1, le=50)
    custom_questions: list[dict] = Field(default_factory=list, max_length=10)
    is_active: bool = True

    @field_validator("slug")
    @classmethod
    def _valid_slug(cls, value: str) -> str:
        slug = cal.normalize_slug(value)
        if not slug or not cal.SLUG_PATTERN.match(slug):
            raise ValueError(
                "slug must be lowercase letters, digits and single hyphens"
            )
        return slug

    @field_validator("duration_minutes")
    @classmethod
    def _allowed_duration(cls, value: int) -> int:
        # Mirrors the CHECK constraint in migration 0021. Validated here too so
        # the user gets a field error instead of a 500 from an IntegrityError.
        if value not in (15, 30, 45, 60):
            raise ValueError("duration_minutes must be one of 15, 30, 45, 60")
        return value


class BookingPagePatchIn(BaseModel):
    """Every field optional; only what is sent is written."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    duration_minutes: int | None = None
    buffer_minutes: int | None = Field(default=None, ge=0, le=120)
    max_bookings_per_day: int | None = Field(default=None, ge=1, le=50)
    custom_questions: list[dict] | None = Field(default=None, max_length=10)
    is_active: bool | None = None

    @field_validator("duration_minutes")
    @classmethod
    def _allowed_duration(cls, value: int | None) -> int | None:
        if value is not None and value not in (15, 30, 45, 60):
            raise ValueError("duration_minutes must be one of 15, 30, 45, 60")
        return value


class BookingPageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    duration_minutes: int
    buffer_minutes: int
    max_bookings_per_day: int | None
    custom_questions: list | None
    is_active: bool


class PublicPageOut(BaseModel):
    """What a STRANGER may see about a booking page.

    A deliberately narrower model than BookingPageOut: no id, no owner, no
    internal counters. The public page needs a title, a description, a length
    and the questions it will ask; anything more is information the visitor
    did not need and we chose to publish.
    """

    slug: str
    title: str
    description: str | None
    duration_minutes: int
    custom_questions: list


class SlotOut(BaseModel):
    start_at: datetime
    end_at: datetime
    date: str


class BookIn(BaseModel):
    start_at: datetime
    invitee_name: str = Field(min_length=1, max_length=200)
    invitee_email: str = Field(min_length=3, max_length=320)
    invitee_phone: str | None = Field(default=None, max_length=50)
    invitee_timezone: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    answers: dict = Field(default_factory=dict)

    @field_validator("invitee_email")
    @classmethod
    def _looks_like_email(cls, value: str) -> str:
        address = value.strip().lower()
        # Deliberately not a full RFC 5322 validator. The address's only job
        # here is to receive a confirmation; a stricter check would reject
        # valid unusual addresses, and a looser one would let through a string
        # with no chance of delivery.
        if "@" not in address or "." not in address.split("@")[-1]:
            raise ValueError("invitee_email must be a valid email address")
        return address


class BookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_page_id: uuid.UUID
    invitee_name: str
    invitee_email: str
    invitee_phone: str | None
    invitee_timezone: str | None
    start_at: datetime
    end_at: datetime
    meeting_link: str | None
    status: BookingStatus
    lead_id: uuid.UUID | None
    notes: str | None
    answers: dict | None


class BookingConfirmationOut(BaseModel):
    """The PUBLIC response to a booking. Confirms, and discloses nothing.

    No lead_id, even though the booking may well have been linked to one:
    echoing it back would turn this endpoint into an oracle for "is this
    address in your CRM?", answerable by anyone who can read a JSON response.
    """

    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    status: BookingStatus
    meeting_link: str | None
    title: str


class BookingPatchIn(BaseModel):
    status: BookingStatus | None = None
    notes: str | None = Field(default=None, max_length=4000)
    meeting_link: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


@router.get("/availability", response_model=list[AvailabilityOut])
def list_availability(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CalendarAvailability]:
    return db.execute(
        select(CalendarAvailability)
        .where(CalendarAvailability.user_id == current_user.id)
        .order_by(CalendarAvailability.day_of_week,
                  CalendarAvailability.start_time)
    ).scalars().all()


@router.put("/availability", response_model=list[AvailabilityOut])
def replace_availability(
    payload: AvailabilityReplaceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CalendarAvailability]:
    """Replace the user's whole weekly availability. See AvailabilityReplaceIn.

    DELETE-then-INSERT in one transaction. Availability rows carry no history
    and nothing references them by id -- bookings store absolute instants, not
    a pointer to the rule that offered them -- so replacing them destroys
    nothing a booking depends on.
    """
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    db.execute(
        delete(CalendarAvailability).where(
            CalendarAvailability.user_id == current_user.id
        )
    )
    rows = [
        CalendarAvailability(
            user_id=current_user.id,
            day_of_week=block.day_of_week,
            start_time=block.start_time,
            end_time=block.end_time,
            timezone=block.timezone,
            is_active=block.is_active,
        )
        for block in payload.blocks
    ]
    db.add_all(rows)
    db.commit()
    return rows


# ---------------------------------------------------------------------------
# Booking pages
# ---------------------------------------------------------------------------


@router.get("/booking-pages", response_model=list[BookingPageOut])
def list_booking_pages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CalendarBookingPage]:
    return db.execute(
        select(CalendarBookingPage)
        .where(CalendarBookingPage.user_id == current_user.id)
        .order_by(CalendarBookingPage.created_at)
    ).scalars().all()


@router.post("/booking-pages", response_model=BookingPageOut, status_code=201)
def create_booking_page(
    payload: BookingPageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalendarBookingPage:
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    page = CalendarBookingPage(
        user_id=current_user.id,
        slug=payload.slug,
        title=payload.title,
        description=payload.description,
        duration_minutes=payload.duration_minutes,
        buffer_minutes=payload.buffer_minutes,
        max_bookings_per_day=payload.max_bookings_per_day,
        custom_questions=payload.custom_questions,
        is_active=payload.is_active,
    )
    db.add(page)
    try:
        db.commit()
    except IntegrityError:
        # The slug is globally unique because it is the public URL. 409 with a
        # message that says what to do, rather than a 500 -- this is the single
        # most likely error a user hits on this form.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"the link /book/{payload.slug} is already taken — "
                   f"choose a different slug",
        ) from None
    return page


@router.patch("/booking-pages/{page_id}", response_model=BookingPageOut)
def update_booking_page(
    page_id: uuid.UUID,
    payload: BookingPagePatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalendarBookingPage:
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    page = cal.owned_booking_page(db, page_id, current_user)
    # The slug is NOT patchable. Changing it silently breaks every link the
    # user has already sent, and the ones already in somebody's calendar
    # invite. Deleting the page and making a new one is the honest way to
    # change a public URL, and it is a decision rather than a typo.
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(page, field, value)
    db.commit()
    return page


@router.delete("/booking-pages/{page_id}", status_code=204)
def delete_booking_page(
    page_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deactivate a booking page. NOT a row delete.

    A hard delete would CASCADE to every booking made through it -- the
    history of meetings that actually happened, and their link to the leads
    they belong to. Deactivating stops new bookings (booking_page_by_slug only
    returns active pages) and keeps all of that.
    """
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    page = cal.owned_booking_page(db, page_id, current_user)
    page.is_active = False
    db.commit()
    return None


# ---------------------------------------------------------------------------
# PUBLIC: the booking page itself
# ---------------------------------------------------------------------------


@router.get("/booking-pages/{slug}/public", response_model=PublicPageOut)
def public_booking_page(slug: str, db: Session = Depends(get_db)) -> dict:
    """PUBLIC — no auth. What /book/{slug} renders before any date is picked."""
    page = cal.booking_page_by_slug(db, slug)
    return {
        "slug": page.slug,
        "title": page.title,
        "description": page.description,
        "duration_minutes": page.duration_minutes,
        "custom_questions": page.custom_questions or [],
    }


@router.get("/booking-pages/{slug}/slots", response_model=list[SlotOut])
def public_slots(
    slug: str,
    timezone_name: str | None = Query(default=None, alias="timezone",
                                      max_length=64),
    days: int = Query(default=30, ge=1, le=90),
    db: Session = Depends(get_db),
) -> list[dict]:
    """PUBLIC — no auth. Bookable slots for the next `days` days.

    Not rate-limited. It is a read with no side effects, and it is what the
    page calls every time the visitor clicks a different date -- limiting it
    would break the booking flow for somebody simply looking at their week.
    """
    page = cal.booking_page_by_slug(db, slug)
    return cal.available_slots(db, page, days=days,
                               invitee_timezone=timezone_name)


@router.post("/booking-pages/{slug}/book",
             response_model=BookingConfirmationOut, status_code=201)
def public_book(
    slug: str,
    payload: BookIn,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """PUBLIC — no auth. Book one slot.

    THREE CHECKS, IN THIS ORDER, AND ALL THREE ARE LOAD-BEARING:
      1. the page is active and public          (booking_page_by_slug)
      2. the slot is one this page is offering  (slot_is_offered)
      3. nobody else has it                     (the UNIQUE constraint)

    (2) rejects a hand-crafted POST for 3am, or a page left open across a
    change to the host's availability. (3) is the one that survives two people
    submitting the same slot in the same second -- see the CalendarBooking
    model docstring for why it is a constraint and not a query.
    """
    enforce_rate_limit(f"ip:{client_ip(request)}", "public_booking",
                       _PUBLIC_LIMIT)

    page = cal.booking_page_by_slug(db, slug)
    start_at = payload.start_at
    if start_at.tzinfo is None:
        # A naive datetime from a browser is ambiguous, and guessing UTC would
        # book somebody into the wrong hour without telling them.
        raise HTTPException(
            status_code=422,
            detail="start_at must include a UTC offset (e.g. "
                   "2026-09-14T10:00:00Z)",
        )
    start_at = start_at.astimezone(timezone.utc)

    if not cal.slot_is_offered(db, page, start_at):
        raise HTTPException(
            status_code=409,
            detail="that time is no longer available — please pick another slot",
        )

    _reject_unanswered_required_questions(page, payload.answers)

    booking = CalendarBooking(
        booking_page_id=page.id,
        invitee_name=payload.invitee_name.strip(),
        invitee_email=payload.invitee_email,
        invitee_phone=payload.invitee_phone,
        invitee_timezone=payload.invitee_timezone,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=page.duration_minutes),
        status=BookingStatus.CONFIRMED,
        notes=payload.notes,
        answers=payload.answers or {},
        slot_key=cal.slot_key_for(start_at),
        # Server-side, and never echoed back — see BookingConfirmationOut.
        lead_id=_matched_lead_id(db, page, payload.invitee_email),
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="that time was just taken — please pick another slot",
        ) from None

    _enqueue_booking_created(booking.id)
    return {
        "id": booking.id,
        "start_at": booking.start_at,
        "end_at": booking.end_at,
        "status": booking.status,
        "meeting_link": booking.meeting_link,
        "title": page.title,
    }


def _matched_lead_id(db: Session, page: CalendarBookingPage, email: str):
    lead = cal.match_lead_by_email(db, page.user_id, email)
    return lead.id if lead is not None else None


def _reject_unanswered_required_questions(page: CalendarBookingPage,
                                          answers: dict) -> None:
    for question in page.custom_questions or []:
        if not isinstance(question, dict) or not question.get("required"):
            continue
        key = str(question.get("key") or "")
        if not str((answers or {}).get(key) or "").strip():
            raise HTTPException(
                status_code=422,
                detail=f"'{question.get('label') or key}' is required",
            )


def _enqueue_booking_created(booking_id: uuid.UUID) -> None:
    """Hand the post-booking work to Celery. Never raises.

    A broker that is down must not fail a booking that is already committed.
    The row exists and shows on the host's calendar either way; what is lost
    is the confirmation email and the CRM linkage, which is a degraded
    booking, not a missing one.
    """
    from app.workers.calendar_tasks import on_booking_created  # noqa: PLC0415

    try:
        on_booking_created.delay(str(booking_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("calendar.post_booking_enqueue_failed",
                       booking_id=str(booking_id), error=str(exc))


# ---------------------------------------------------------------------------
# Bookings (authenticated)
# ---------------------------------------------------------------------------


@router.get("/bookings", response_model=list[BookingOut])
def list_bookings(
    start_from: datetime | None = None,
    start_to: datetime | None = None,
    status: BookingStatus | None = None,
    lead_id: uuid.UUID | None = None,
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CalendarBooking]:
    """Every booking on this user's pages, filtered.

    Scoped by a subquery over the user's own pages rather than a join, so
    there is exactly one expression of "mine" in this handler and no way to
    forget it in a later filter branch.
    """
    pages = select(CalendarBookingPage.id).where(
        CalendarBookingPage.user_id == current_user.id
    )
    query = select(CalendarBooking).where(
        CalendarBooking.booking_page_id.in_(pages)
    )
    if start_from is not None:
        query = query.where(CalendarBooking.start_at >= start_from)
    if start_to is not None:
        query = query.where(CalendarBooking.start_at < start_to)
    if status is not None:
        query = query.where(CalendarBooking.status == status)
    if lead_id is not None:
        query = query.where(CalendarBooking.lead_id == lead_id)
    return db.execute(
        query.order_by(CalendarBooking.start_at).limit(limit)
    ).scalars().all()


@router.get("/bookings/{booking_id}", response_model=BookingOut)
def get_booking(
    booking_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalendarBooking:
    return cal.owned_booking(db, booking_id, current_user)


@router.patch("/bookings/{booking_id}", response_model=BookingOut)
def update_booking(
    booking_id: uuid.UUID,
    payload: BookingPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CalendarBooking:
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    booking = cal.owned_booking(db, booking_id, current_user)
    fields = payload.model_dump(exclude_unset=True)
    new_status = fields.pop("status", None)
    for field, value in fields.items():
        setattr(booking, field, value)

    if new_status is not None and new_status != booking.status:
        booking.status = new_status
        # slot_key tracks whether the slot is HELD, so it has to move with the
        # status: a cancelled or no-show booking releases its time (NULL), and
        # anything else holds it. Doing this here rather than only in the
        # DELETE handler means the grid's inline status change cannot leave a
        # cancelled booking silently blocking the calendar.
        booking.slot_key = (
            None if new_status in (BookingStatus.CANCELLED, BookingStatus.NO_SHOW)
            else cal.slot_key_for(booking.start_at)
        )
        if new_status is BookingStatus.CANCELLED:
            _enqueue_cancellation(booking.id, reason="cancelled by the host")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="another live booking already holds that slot",
        ) from None
    return booking


@router.delete("/bookings/{booking_id}", status_code=204)
def cancel_booking(
    booking_id: uuid.UUID,
    reason: str | None = Query(default=None, max_length=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """SOFT delete: status=cancelled, slot released, cancellation email sent.

    Never a row delete. The booking is the record that a meeting was arranged
    with this person -- it is on their lead's timeline, it may have a meeting
    and a transcript hanging off it, and it is what an outcome row points at.
    """
    enforce_rate_limit(str(current_user.id), "calendar_write", _WRITE_LIMIT)

    booking = cal.owned_booking(db, booking_id, current_user)
    if booking.status is BookingStatus.CANCELLED:
        # Already cancelled: idempotent, and no second cancellation email to
        # somebody who has already been told once.
        return None
    booking.status = BookingStatus.CANCELLED
    booking.slot_key = None
    db.commit()
    _enqueue_cancellation(booking.id, reason=reason)
    return None


def _enqueue_cancellation(booking_id: uuid.UUID, reason: str | None) -> None:
    from app.workers.calendar_tasks import on_booking_cancelled  # noqa: PLC0415

    try:
        on_booking_cancelled.delay(str(booking_id), reason)
    except Exception as exc:  # noqa: BLE001 — see _enqueue_booking_created
        logger.warning("calendar.cancellation_enqueue_failed",
                       booking_id=str(booking_id), error=str(exc))
