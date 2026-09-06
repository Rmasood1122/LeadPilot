"""Engagement Hub, Feature 2 — the calendar: availability, slots, bookings.

The three things worth testing here, in order of how much they would cost if
they were wrong:

  1. DOUBLE BOOKING. Two people submitting the same slot must produce one
     booking and one 409, and it must be the UNIQUE constraint that decides —
     not a check-then-insert that loses the race in production and passes here.
  2. TENANCY. A booking page, its bookings and the lead auto-link are all
     scoped to one account. The unscoped version of the lead lookup is the
     exact bug app/api/webhooks.py and outreach_tasks.py were both fixed for.
  3. SLOT ARITHMETIC. Availability rules minus existing bookings minus the
     per-day cap, in the right time zone, for the right days.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

import pytest

from app.db import models as m
from app.services import calendar_service as cal

UTC = timezone.utc


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def no_broker(monkeypatch):
    """Record the post-booking task instead of publishing it.

    The root suite has no broker (see tests/conftest.py). The endpoint already
    swallows an enqueue failure — a booking must survive a broker outage — so
    without this the tests would pass while silently exercising the failure
    path, and a bug that stopped the task being enqueued at all would be
    invisible. Recording it means the enqueue itself is under test.
    """
    from app.workers import calendar_tasks

    calls: list[tuple[str, tuple]] = []
    monkeypatch.setattr(calendar_tasks.on_booking_created, "delay",
                        lambda *a, **k: calls.append(("created", a)),
                        raising=False)
    monkeypatch.setattr(calendar_tasks.on_booking_cancelled, "delay",
                        lambda *a, **k: calls.append(("cancelled", a)),
                        raising=False)
    return calls


@pytest.fixture()
def availability(db_session, test_user):
    """Mon–Fri, 09:00–17:00 UTC."""
    rows = [
        m.CalendarAvailability(
            user_id=test_user.id, day_of_week=day,
            start_time=time(9, 0), end_time=time(17, 0),
            timezone="UTC", is_active=True,
        )
        for day in range(5)
    ]
    db_session.add_all(rows)
    db_session.commit()
    return rows


@pytest.fixture()
def booking_page(db_session, test_user, availability):
    page = m.CalendarBookingPage(
        user_id=test_user.id, slug="intro-call", title="Intro call",
        duration_minutes=30, buffer_minutes=0, is_active=True,
    )
    db_session.add(page)
    db_session.commit()
    return page


def _starts(slots: list[dict]) -> set[datetime]:
    """Slot start instants as datetimes.

    NOT as the strings the API returns. FastAPI serialises UTC as "...Z" and
    `datetime.isoformat()` produces "+00:00", so a `target.isoformat() not in
    [s["start_at"] ...]` assertion is true no matter what the endpoint did --
    it passed on the first run of this file for exactly that reason, while
    proving nothing.
    """
    return {datetime.fromisoformat(slot["start_at"]) for slot in slots}


def _next_weekday(base: datetime, weekday: int) -> datetime:
    """The next date strictly after `base` falling on `weekday` (0=Mon)."""
    ahead = (weekday - base.weekday()) % 7 or 7
    return (base + timedelta(days=ahead)).replace(
        hour=10, minute=0, second=0, microsecond=0
    )


# --------------------------------------------------------------------------
# Availability
# --------------------------------------------------------------------------


class TestAvailability:
    def test_put_replaces_the_whole_week(self, client, db_session, availability):
        resp = client.put("/calendar/availability", json={"blocks": [
            {"day_of_week": 2, "start_time": "13:00", "end_time": "18:00",
             "timezone": "Asia/Karachi", "is_active": True},
        ]})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        remaining = db_session.query(m.CalendarAvailability).all()
        assert len(remaining) == 1, "the previous five blocks should be gone"
        assert remaining[0].timezone == "Asia/Karachi"

    def test_end_before_start_is_rejected(self, client):
        """An overnight window is not supported, and silently treating it as
        'all day' would offer the user's 3am."""
        resp = client.put("/calendar/availability", json={"blocks": [
            {"day_of_week": 0, "start_time": "17:00", "end_time": "09:00",
             "timezone": "UTC", "is_active": True},
        ]})
        assert resp.status_code == 422

    def test_an_unknown_timezone_is_rejected(self, client):
        """Not coerced to UTC: a rule written in 'Europe/Lundon' would offer
        slots at the wrong hour forever with nothing saying so."""
        resp = client.put("/calendar/availability", json={"blocks": [
            {"day_of_week": 0, "start_time": "09:00", "end_time": "17:00",
             "timezone": "Europe/Lundon", "is_active": True},
        ]})
        assert resp.status_code == 422

    def test_day_of_week_is_bounded(self, client):
        resp = client.put("/calendar/availability", json={"blocks": [
            {"day_of_week": 7, "start_time": "09:00", "end_time": "17:00",
             "timezone": "UTC", "is_active": True},
        ]})
        assert resp.status_code == 422

    def test_another_users_availability_is_invisible(
        self, client, db_session, availability
    ):
        other = m.User(email="other@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        db_session.add(m.CalendarAvailability(
            user_id=other.id, day_of_week=6, start_time=time(1, 0),
            end_time=time(2, 0), timezone="UTC", is_active=True,
        ))
        db_session.commit()

        rows = client.get("/calendar/availability").json()
        assert all(row["day_of_week"] != 6 for row in rows)


# --------------------------------------------------------------------------
# Booking pages
# --------------------------------------------------------------------------


class TestBookingPages:
    def test_create_and_list(self, client, availability):
        resp = client.post("/calendar/booking-pages", json={
            "slug": "Deep Dive!", "title": "Deep dive",
            "duration_minutes": 60,
        })
        assert resp.status_code == 201
        # The slug is normalised, not rejected: a title pasted into the field
        # should still produce a usable link.
        assert resp.json()["slug"] == "deep-dive"

        assert any(p["slug"] == "deep-dive"
                   for p in client.get("/calendar/booking-pages").json())

    def test_a_duplicate_slug_is_a_409_not_a_500(self, client, booking_page):
        """The slug is the public URL and is globally unique, so this is the
        single most likely error on the form. It has to say what to do."""
        resp = client.post("/calendar/booking-pages", json={
            "slug": "intro-call", "title": "Another one",
            "duration_minutes": 30,
        })
        assert resp.status_code == 409
        assert "already taken" in resp.json()["detail"]

    def test_only_the_four_durations_are_accepted(self, client):
        resp = client.post("/calendar/booking-pages", json={
            "slug": "odd", "title": "Odd", "duration_minutes": 37,
        })
        assert resp.status_code == 422

    def test_delete_deactivates_and_keeps_the_bookings(
        self, client, db_session, booking_page
    ):
        """A hard delete would CASCADE to every meeting ever booked through
        the page — the history, and its link to the leads it belongs to."""
        start = datetime.now(UTC) + timedelta(days=3)
        db_session.add(m.CalendarBooking(
            booking_page_id=booking_page.id, invitee_name="Sam",
            invitee_email="sam@acme.test", start_at=start,
            end_at=start + timedelta(minutes=30),
            status=m.BookingStatus.CONFIRMED,
            slot_key=cal.slot_key_for(start),
        ))
        db_session.commit()

        assert client.delete(
            f"/calendar/booking-pages/{booking_page.id}"
        ).status_code == 204

        db_session.refresh(booking_page)
        assert booking_page.is_active is False
        assert db_session.query(m.CalendarBooking).count() == 1

    def test_another_users_page_is_404_not_403(self, client, db_session):
        """404 so a probe cannot tell 'not yours' from 'does not exist'."""
        other = m.User(email="other2@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        page = m.CalendarBookingPage(
            user_id=other.id, slug="theirs", title="Theirs",
            duration_minutes=30,
        )
        db_session.add(page)
        db_session.commit()

        assert client.patch(f"/calendar/booking-pages/{page.id}",
                            json={"title": "Mine now"}).status_code == 404


# --------------------------------------------------------------------------
# Public slots
# --------------------------------------------------------------------------


class TestPublicSlots:
    def test_slots_are_public_and_respect_the_window(
        self, anon_client, booking_page
    ):
        slots = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=7"
        ).json()
        assert slots, "a Mon-Fri 9-5 rule should produce slots within a week"
        for slot in slots:
            start = datetime.fromisoformat(slot["start_at"])
            assert 9 <= start.astimezone(UTC).hour < 17
            assert start.weekday() < 5

    def test_slots_are_spaced_by_duration_plus_buffer(
        self, anon_client, db_session, booking_page
    ):
        booking_page.buffer_minutes = 15
        db_session.commit()

        slots = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=7"
        ).json()
        same_day = [s for s in slots if s["date"] == slots[0]["date"]]
        first = datetime.fromisoformat(same_day[0]["start_at"])
        second = datetime.fromisoformat(same_day[1]["start_at"])
        assert second - first == timedelta(minutes=45)

    def test_an_existing_booking_removes_its_slot(
        self, anon_client, db_session, booking_page
    ):
        before = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=14"
        ).json()
        target = datetime.fromisoformat(before[3]["start_at"])

        db_session.add(m.CalendarBooking(
            booking_page_id=booking_page.id, invitee_name="Taken",
            invitee_email="taken@acme.test", start_at=target,
            end_at=target + timedelta(minutes=30),
            status=m.BookingStatus.CONFIRMED,
            slot_key=cal.slot_key_for(target),
        ))
        db_session.commit()

        after = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=14"
        ).json()
        assert target not in _starts(after)

    def test_a_meeting_with_no_booking_also_blocks_a_slot(
        self, anon_client, db_session, booking_page, test_user
    ):
        """The manual path: a meeting created from a time agreed over email
        has no booking behind it, and the host is still busy."""
        before = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=14"
        ).json()
        target = datetime.fromisoformat(before[2]["start_at"])

        db_session.add(m.Meeting(
            host_user_id=test_user.id, platform=m.MeetingPlatform.CUSTOM,
            start_at=target, end_at=target + timedelta(minutes=30),
            status=m.MeetingStatus.SCHEDULED,
        ))
        db_session.commit()

        after = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=14"
        ).json()
        assert target not in _starts(after)

    def test_a_cancelled_booking_frees_its_slot_again(
        self, anon_client, db_session, booking_page
    ):
        slots = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=14"
        ).json()
        target = datetime.fromisoformat(slots[1]["start_at"])

        booking = m.CalendarBooking(
            booking_page_id=booking_page.id, invitee_name="Gone",
            invitee_email="gone@acme.test", start_at=target,
            end_at=target + timedelta(minutes=30),
            status=m.BookingStatus.CANCELLED, slot_key=None,
        )
        db_session.add(booking)
        db_session.commit()

        after = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=14"
        ).json()
        assert target in _starts(after)

    def test_the_per_day_cap_is_enforced(
        self, anon_client, db_session, booking_page
    ):
        booking_page.max_bookings_per_day = 1
        db_session.commit()

        slots = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=14"
        ).json()
        first_day = slots[0]["date"]
        target = datetime.fromisoformat(slots[0]["start_at"])

        db_session.add(m.CalendarBooking(
            booking_page_id=booking_page.id, invitee_name="One",
            invitee_email="one@acme.test", start_at=target,
            end_at=target + timedelta(minutes=30),
            status=m.BookingStatus.CONFIRMED,
            slot_key=cal.slot_key_for(target),
        ))
        db_session.commit()

        after = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=14"
        ).json()
        assert all(s["date"] != first_day for s in after), (
            "the day is full, so NO slot on it should still be offered"
        )

    def test_an_inactive_page_is_404_like_a_missing_one(
        self, anon_client, db_session, booking_page
    ):
        """Answering 'paused' would confirm the slug exists to anyone
        enumerating them, and no visitor can act on the distinction."""
        booking_page.is_active = False
        db_session.commit()
        assert anon_client.get(
            "/calendar/booking-pages/intro-call/slots"
        ).status_code == 404

    def test_the_public_page_discloses_nothing_extra(
        self, anon_client, booking_page
    ):
        body = anon_client.get(
            "/calendar/booking-pages/intro-call/public"
        ).json()
        assert set(body) == {"slug", "title", "description",
                             "duration_minutes", "custom_questions"}


# --------------------------------------------------------------------------
# Booking
# --------------------------------------------------------------------------


class TestBooking:
    def _first_slot(self, anon_client) -> str:
        slots = anon_client.get(
            "/calendar/booking-pages/intro-call/slots?days=14"
        ).json()
        assert slots
        return slots[0]["start_at"]

    def test_a_visitor_can_book(self, anon_client, db_session, booking_page,
                                no_broker):
        start = self._first_slot(anon_client)
        resp = anon_client.post("/calendar/booking-pages/intro-call/book", json={
            "start_at": start, "invitee_name": "Sara Khan",
            "invitee_email": "Sara@Acme.test", "invitee_timezone": "Asia/Karachi",
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "confirmed"
        # The confirmation must not leak CRM state — see BookingConfirmationOut.
        assert "lead_id" not in body

        booking = db_session.query(m.CalendarBooking).one()
        assert booking.invitee_email == "sara@acme.test", "email is normalised"
        assert booking.slot_key == cal.slot_key_for(
            datetime.fromisoformat(start)
        )
        assert ("created", (str(booking.id),)) in no_broker

    def test_double_booking_is_refused_by_the_constraint(
        self, anon_client, db_session, booking_page
    ):
        """The second insert must fail on UNIQUE (booking_page_id, slot_key),
        not on a re-read of the slot list — that is what survives two requests
        arriving in the same second."""
        start = self._first_slot(anon_client)
        payload = {"start_at": start, "invitee_name": "First",
                   "invitee_email": "first@acme.test"}
        assert anon_client.post(
            "/calendar/booking-pages/intro-call/book", json=payload
        ).status_code == 201

        # Insert the duplicate DIRECTLY, bypassing the availability check, so
        # what is being tested is the constraint and nothing else.
        from sqlalchemy.exc import IntegrityError

        parsed = datetime.fromisoformat(start)
        db_session.add(m.CalendarBooking(
            booking_page_id=booking_page.id, invitee_name="Second",
            invitee_email="second@acme.test", start_at=parsed,
            end_at=parsed + timedelta(minutes=30),
            status=m.BookingStatus.CONFIRMED,
            slot_key=cal.slot_key_for(parsed),
        ))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_booking_a_slot_that_is_not_offered_is_409(
        self, anon_client, booking_page
    ):
        """A hand-crafted POST for 3am, or a page left open across a change to
        the availability rules."""
        at_3am = (datetime.now(UTC) + timedelta(days=2)).replace(
            hour=3, minute=0, second=0, microsecond=0
        )
        resp = anon_client.post("/calendar/booking-pages/intro-call/book", json={
            "start_at": at_3am.isoformat(), "invitee_name": "Night owl",
            "invitee_email": "owl@acme.test",
        })
        assert resp.status_code == 409

    def test_a_naive_start_at_is_rejected(self, anon_client, booking_page):
        """Guessing UTC would book somebody into the wrong hour silently."""
        start = self._first_slot(anon_client)
        naive = datetime.fromisoformat(start).replace(tzinfo=None).isoformat()
        resp = anon_client.post("/calendar/booking-pages/intro-call/book", json={
            "start_at": naive, "invitee_name": "X", "invitee_email": "x@acme.test",
        })
        assert resp.status_code == 422

    def test_a_required_question_must_be_answered(
        self, anon_client, db_session, booking_page
    ):
        booking_page.custom_questions = [
            {"key": "budget", "label": "Budget?", "required": True}
        ]
        db_session.commit()

        start = self._first_slot(anon_client)
        base = {"start_at": start, "invitee_name": "Q",
                "invitee_email": "q@acme.test"}
        assert anon_client.post(
            "/calendar/booking-pages/intro-call/book", json=base
        ).status_code == 422
        assert anon_client.post(
            "/calendar/booking-pages/intro-call/book",
            json={**base, "answers": {"budget": "3k"}},
        ).status_code == 201

    def test_the_lead_link_is_scoped_to_the_page_owner(
        self, anon_client, db_session, booking_page, verified_strategy,
        test_user,
    ):
        """The unscoped version of this lookup is the cross-tenant bug that
        was fixed in the Calendly webhook and the inbound-reply router. Two
        customers prospecting the same person is routine in B2B."""
        mine = m.Lead(strategy_id=verified_strategy.id, source="manual",
                      email="sara@acme.test", full_name="Sara")
        db_session.add(mine)

        stranger = m.User(email="stranger@leadpilot.dev", email_verified=True)
        db_session.add(stranger)
        db_session.flush()
        their_product = m.Product(user_id=stranger.id, name="Theirs",
                                  description="x", type=m.ProductType.SKILL)
        db_session.add(their_product)
        db_session.flush()
        their_strategy = m.Strategy(product_id=their_product.id,
                                    flow_type=m.FlowType.WITH_CLIENTS)
        db_session.add(their_strategy)
        db_session.flush()
        theirs = m.Lead(strategy_id=their_strategy.id, source="manual",
                        email="sara@acme.test", full_name="Sara")
        db_session.add(theirs)
        db_session.commit()

        start = self._first_slot(anon_client)
        anon_client.post("/calendar/booking-pages/intro-call/book", json={
            "start_at": start, "invitee_name": "Sara",
            "invitee_email": "sara@acme.test",
        })
        booking = db_session.query(m.CalendarBooking).one()
        assert booking.lead_id == mine.id
        assert booking.lead_id != theirs.id

    def test_an_unmatched_invitee_books_without_a_lead(
        self, anon_client, db_session, booking_page
    ):
        start = self._first_slot(anon_client)
        assert anon_client.post(
            "/calendar/booking-pages/intro-call/book",
            json={"start_at": start, "invitee_name": "Nobody",
                  "invitee_email": "nobody@elsewhere.test"},
        ).status_code == 201
        assert db_session.query(m.CalendarBooking).one().lead_id is None


# --------------------------------------------------------------------------
# Managing bookings
# --------------------------------------------------------------------------


class TestManagingBookings:
    @pytest.fixture()
    def booking(self, db_session, booking_page):
        start = _next_weekday(datetime.now(UTC), 2)
        row = m.CalendarBooking(
            booking_page_id=booking_page.id, invitee_name="Sam",
            invitee_email="sam@acme.test", start_at=start,
            end_at=start + timedelta(minutes=30),
            status=m.BookingStatus.CONFIRMED,
            slot_key=cal.slot_key_for(start),
        )
        db_session.add(row)
        db_session.commit()
        return row

    def test_list_and_filter(self, client, booking):
        assert len(client.get("/calendar/bookings").json()) == 1
        assert client.get(
            "/calendar/bookings?status=cancelled"
        ).json() == []

    def test_cancel_is_soft_and_releases_the_slot(
        self, client, db_session, booking, no_broker
    ):
        assert client.delete(
            f"/calendar/bookings/{booking.id}?reason=conflict"
        ).status_code == 204

        db_session.refresh(booking)
        assert booking.status is m.BookingStatus.CANCELLED
        assert booking.slot_key is None, (
            "a cancelled booking must stop blocking its slot"
        )
        assert db_session.query(m.CalendarBooking).count() == 1
        assert ("cancelled", (str(booking.id), "conflict")) in no_broker

    def test_cancelling_twice_sends_one_email(
        self, client, booking, no_broker
    ):
        client.delete(f"/calendar/bookings/{booking.id}")
        client.delete(f"/calendar/bookings/{booking.id}")
        assert sum(1 for kind, _ in no_broker if kind == "cancelled") == 1

    def test_marking_no_show_also_releases_the_slot(
        self, client, db_session, booking
    ):
        """The grid's inline status change must not leave a call that did not
        happen blocking the host's calendar."""
        resp = client.patch(f"/calendar/bookings/{booking.id}",
                            json={"status": "no_show"})
        assert resp.status_code == 200
        db_session.refresh(booking)
        assert booking.slot_key is None

    def test_another_users_booking_is_404(self, client, db_session):
        other = m.User(email="other3@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        page = m.CalendarBookingPage(user_id=other.id, slug="theirs2",
                                     title="Theirs", duration_minutes=30)
        db_session.add(page)
        db_session.flush()
        start = datetime.now(UTC) + timedelta(days=1)
        row = m.CalendarBooking(
            booking_page_id=page.id, invitee_name="Not yours",
            invitee_email="x@x.test", start_at=start,
            end_at=start + timedelta(minutes=30),
            status=m.BookingStatus.CONFIRMED,
        )
        db_session.add(row)
        db_session.commit()

        assert client.get(f"/calendar/bookings/{row.id}").status_code == 404
        assert client.delete(f"/calendar/bookings/{row.id}").status_code == 404


# --------------------------------------------------------------------------
# Slot maths, directly
# --------------------------------------------------------------------------


class TestSlotService:
    def test_slot_key_normalises_equivalent_instants(self):
        """Two clients can describe the same moment as 10:00Z and 11:00+01:00.
        If the key differed, the UNIQUE constraint would let both in."""
        a = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)
        b = datetime(2026, 9, 14, 11, 0,
                     tzinfo=timezone(timedelta(hours=1)))
        assert cal.slot_key_for(a) == cal.slot_key_for(b)

    def test_minimum_notice_is_respected(self, db_session, booking_page):
        """A slot starting in ninety seconds, in a meeting the host is
        already in, with no notification, is not a slot."""
        from app.config import settings

        now = datetime.now(UTC)
        slots = cal.available_slots(db_session, booking_page, days=2, now=now)
        earliest = now + timedelta(minutes=settings.calendar_min_notice_minutes)
        assert all(slot["start_at"] >= earliest for slot in slots)

    def test_wall_clock_times_survive_a_dst_change(self, db_session, test_user):
        """A rule written as 9am London stays 9am London across the October
        change — stored as UTC it would silently become 8am or 10am."""
        db_session.query(m.CalendarAvailability).delete()
        db_session.add(m.CalendarAvailability(
            user_id=test_user.id, day_of_week=2,
            start_time=time(9, 0), end_time=time(10, 0),
            timezone="Europe/London", is_active=True,
        ))
        page = m.CalendarBookingPage(user_id=test_user.id, slug="dst",
                                     title="DST", duration_minutes=60)
        db_session.add(page)
        db_session.commit()

        # A window spanning the last Sunday in October 2026.
        before = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
        slots = cal.available_slots(db_session, page, days=21, now=before)
        from zoneinfo import ZoneInfo

        london = ZoneInfo("Europe/London")
        hours = {slot["start_at"].astimezone(london).hour for slot in slots}
        assert hours == {9}, f"expected every slot at 9am local, got {hours}"

    def test_no_availability_means_no_slots(self, db_session, test_user):
        db_session.query(m.CalendarAvailability).delete()
        page = m.CalendarBookingPage(user_id=test_user.id, slug="empty",
                                     title="Empty", duration_minutes=30)
        db_session.add(page)
        db_session.commit()
        assert cal.available_slots(db_session, page) == []

    def test_resolve_timezone_never_raises(self):
        assert cal.resolve_timezone(None) is not None
        assert cal.resolve_timezone("Not/AZone") is not None
        assert str(cal.resolve_timezone("Asia/Karachi")) == "Asia/Karachi"
