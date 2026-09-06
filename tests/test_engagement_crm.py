"""Engagement Hub, Feature 4 — bookings and meetings reaching the CRM.

Three things, each of which is a silent failure if it stops working:

  * A booking must move the lead, write ONE outcome, land on the timeline and
    PAUSE the sequence. Not stop it — pause, so a cancellation puts a warm
    lead back into outreach instead of stranding it in a state the engine
    defines as irreversible.
  * A completed meeting must attach its summary where a user will actually
    read it before their next touch, and turn OUR commitments into tasks.
  * `outcomes` and `crm_activities` stay separate. The M8 learning loop
    computes rates from `outcomes` row counts; a booking writing twice there,
    or writing "note added" noise into it, changes those denominators
    silently.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.services import calendar_service as cal
from app.services import crm_events
from app.services import sequence_engine as engine
from app.workers import calendar_tasks

UTC = timezone.utc


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def lead(db_session, verified_strategy):
    row = m.Lead(strategy_id=verified_strategy.id, source="manual",
                 full_name="Sara Khan", company="Acme Fire",
                 email="sara@acme.test", status=m.LeadStatus.CONTACTED)
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture()
def enrolled(db_session, verified_strategy, lead):
    """A live sequence with a message queued for tomorrow."""
    seq = m.Sequence(strategy_id=verified_strategy.id,
                     channel=m.ChannelType.EMAIL, name="Outbound",
                     status=m.SequenceStatus.ACTIVE)
    db_session.add(seq)
    db_session.flush()
    db_session.add(m.SequenceStep(sequence_id=seq.id, step_no=1,
                                  template="Open on X", delay_days=0))
    enrollment = m.SequenceEnrollment(sequence_id=seq.id, lead_id=lead.id,
                                      status=m.EnrollmentStatus.ACTIVE)
    db_session.add(enrollment)
    db_session.flush()
    db_session.add(m.Message(
        sequence_id=seq.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
        step_no=1, template="Open on X", status=m.MessageStatus.SCHEDULED,
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
    ))
    db_session.commit()
    return enrollment


@pytest.fixture()
def availability_utc(db_session, test_user):
    """The host's zone comes from their availability rows (_host_timezone).
    Without one the fallback is UTC anyway, but stating it makes the
    timezone assertion below test the lookup rather than the fallback."""
    from datetime import time as _time

    row = m.CalendarAvailability(
        user_id=test_user.id, day_of_week=0, start_time=_time(9, 0),
        end_time=_time(17, 0), timezone="UTC", is_active=True,
    )
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture()
def booking(db_session, test_user, lead):
    page = m.CalendarBookingPage(user_id=test_user.id, slug="intro",
                                 title="Intro call", duration_minutes=30)
    db_session.add(page)
    db_session.flush()
    start = datetime.now(UTC) + timedelta(days=2)
    row = m.CalendarBooking(
        booking_page_id=page.id, invitee_name="Sara Khan",
        invitee_email="sara@acme.test", start_at=start,
        end_at=start + timedelta(minutes=30),
        status=m.BookingStatus.CONFIRMED, lead_id=lead.id,
        invitee_timezone="Asia/Karachi",
        slot_key=cal.slot_key_for(start),
    )
    db_session.add(row)
    db_session.commit()
    return row


# --------------------------------------------------------------------------
# Booking -> CRM
# --------------------------------------------------------------------------


class TestBookingCreated:
    def test_it_moves_the_lead_and_files_the_event(
        self, db_session, booking, lead, mailbox
    ):
        assert calendar_tasks.on_booking_created_impl(
            db_session, booking.id) == "ok"

        db_session.refresh(lead)
        assert lead.status is m.LeadStatus.MEETING_BOOKED

        outcome = db_session.query(m.Outcome).filter_by(
            event=m.OutcomeEvent.BOOKED).one()
        assert outcome.channel == "leadpilot_calendar"
        assert outcome.meta_json["booking_id"] == str(booking.id)
        # Denormalized for the learning loop's GROUP BY.
        assert outcome.strategy_id == lead.strategy_id

        activity = db_session.query(m.CrmActivity).filter_by(
            kind=m.CrmActivityKind.MEETING_BOOKED).one()
        assert activity.meta_json["booking_id"] == str(booking.id)
        assert activity.strategy_id == lead.strategy_id

    def test_exactly_one_outcome_row_is_written(
        self, db_session, booking, mailbox
    ):
        """`outcomes` feeds the M8 learning loop, which computes rates from
        row counts. Two BOOKED rows for one booking would inflate the booking
        rate for that strategy, permanently and silently."""
        calendar_tasks.on_booking_created_impl(db_session, booking.id)
        assert db_session.query(m.Outcome).filter_by(
            event=m.OutcomeEvent.BOOKED).count() == 1

    def test_both_parties_are_emailed(self, db_session, booking, mailbox,
                                      test_user):
        calendar_tasks.on_booking_created_impl(db_session, booking.id)
        recipients = {msg["to"] for msg in mailbox}
        assert booking.invitee_email in recipients
        assert test_user.email in recipients

    def test_the_invitee_is_told_the_time_in_THEIR_zone(
        self, db_session, booking, mailbox
    ):
        """A confirmation that makes somebody convert a time by hand is a
        confirmation somebody turns up an hour late to."""
        calendar_tasks.on_booking_created_impl(db_session, booking.id)
        to_invitee = next(m_ for m_ in mailbox
                          if m_["to"] == booking.invitee_email)
        assert "Asia/Karachi" in to_invitee["text"]

    def test_the_sequence_is_paused_not_stopped(
        self, db_session, booking, lead, enrolled, mailbox
    ):
        """PAUSED, so a cancelled meeting can put this lead back into
        outreach. A stopped enrollment can never send again — see
        sequence_engine.pause_for_meeting for why this path differs from the
        Calendly one."""
        calendar_tasks.on_booking_created_impl(db_session, booking.id)

        db_session.refresh(enrolled)
        assert enrolled.status is m.EnrollmentStatus.PAUSED
        assert enrolled.stop_reason == engine.MEETING_PAUSE_REASON
        assert enrolled.paused_until is not None

    def test_the_pending_message_is_pushed_past_the_meeting(
        self, db_session, booking, enrolled, mailbox
    ):
        """Sending a cold nudge to somebody who has a call with you booked
        for Thursday is the exact thing this pause exists to prevent."""
        calendar_tasks.on_booking_created_impl(db_session, booking.id)
        msg = db_session.query(m.Message).one()
        scheduled = msg.scheduled_at
        if scheduled.tzinfo is None:
            scheduled = scheduled.replace(tzinfo=UTC)
        assert scheduled > booking.end_at

    def test_a_stopped_enrollment_is_never_resurrected(
        self, db_session, booking, enrolled, mailbox
    ):
        """A lead who unsubscribed and later booked through a colleague's
        link must not have their outreach quietly restarted."""
        enrolled.status = m.EnrollmentStatus.STOPPED
        enrolled.stop_reason = "unsubscribed"
        db_session.commit()

        calendar_tasks.on_booking_created_impl(db_session, booking.id)
        db_session.refresh(enrolled)
        assert enrolled.status is m.EnrollmentStatus.STOPPED

    def test_a_booking_with_no_lead_still_confirms(
        self, db_session, booking, mailbox
    ):
        booking.lead_id = None
        db_session.commit()
        assert calendar_tasks.on_booking_created_impl(
            db_session, booking.id) == "ok"
        assert mailbox, "the invitee must still get their confirmation"
        assert db_session.query(m.Outcome).count() == 0

    def test_a_missing_booking_is_not_an_error(self, db_session):
        assert calendar_tasks.on_booking_created_impl(
            db_session, uuid.uuid4()) == "missing"


class TestBookingCancelled:
    def test_the_lead_goes_back_to_replied_and_outreach_resumes(
        self, db_session, booking, lead, enrolled, mailbox
    ):
        calendar_tasks.on_booking_created_impl(db_session, booking.id)
        booking.status = m.BookingStatus.CANCELLED
        booking.slot_key = None
        db_session.commit()

        calendar_tasks.on_booking_cancelled_impl(db_session, booking.id,
                                                 reason="clash")

        db_session.refresh(lead)
        db_session.refresh(enrolled)
        assert lead.status is m.LeadStatus.REPLIED
        assert enrolled.status is m.EnrollmentStatus.ACTIVE
        assert enrolled.stop_reason is None

    def test_it_does_not_resume_an_out_of_office_pause(
        self, db_session, booking, lead, enrolled, mailbox
    ):
        """A cancelled meeting says nothing about an inbox the engine has
        been told is unattended. Only pauses THIS feature made are undone."""
        engine.pause_enrollment(db_session, enrolled,
                                until=datetime.now(UTC) + timedelta(days=7))
        db_session.commit()

        calendar_tasks.on_booking_cancelled_impl(db_session, booking.id)
        db_session.refresh(enrolled)
        assert enrolled.status is m.EnrollmentStatus.PAUSED

    def test_both_parties_are_told(self, db_session, booking, mailbox,
                                   test_user):
        calendar_tasks.on_booking_cancelled_impl(db_session, booking.id)
        recipients = {msg["to"] for msg in mailbox}
        assert booking.invitee_email in recipients
        assert test_user.email in recipients

    def test_each_party_is_told_the_time_in_THEIR_zone(
        self, db_session, booking, mailbox, test_user, availability_utc
    ):
        """Caught running the stack locally: the cancellation path computed a
        single `when` in the invitee's zone and sent it to both, so a host
        whose calendar said 09:30 UTC was told their "10:30 (Europe/London)"
        meeting was cancelled. The confirmation path never had this bug."""
        booking.invitee_timezone = "Asia/Karachi"
        db_session.commit()

        calendar_tasks.on_booking_cancelled_impl(db_session, booking.id)
        to_invitee = next(m_ for m_ in mailbox
                          if m_["to"] == booking.invitee_email)
        to_host = next(m_ for m_ in mailbox if m_["to"] == test_user.email)

        assert "Asia/Karachi" in to_invitee["text"]
        assert "(UTC)" in to_host["text"]
        assert "Asia/Karachi" not in to_host["text"]


# --------------------------------------------------------------------------
# Meeting -> CRM
# --------------------------------------------------------------------------


class TestMeetingCompleted:
    @pytest.fixture()
    def meeting(self, db_session, test_user, lead, booking):
        row = m.Meeting(
            booking_id=booking.id, host_user_id=test_user.id, lead_id=lead.id,
            platform=m.MeetingPlatform.CUSTOM, title="Intro — Sara Khan",
            start_at=booking.start_at, end_at=booking.end_at,
            actual_start_at=booking.start_at,
            actual_end_at=booking.start_at + timedelta(minutes=22),
            status=m.MeetingStatus.COMPLETED,
            transcript="Sara: onboarding takes two weeks.",
            raw_notes="budget approved",
        )
        db_session.add(row)
        db_session.commit()
        return row

    def test_the_summary_is_filed_where_a_user_will_read_it(
        self, db_session, meeting, lead, fake_claude
    ):
        assert calendar_tasks.generate_summary_impl(
            db_session, meeting.id) == "ok"

        db_session.refresh(meeting)
        assert meeting.summary
        assert meeting.key_points
        assert meeting.sentiment == "positive"

        activity = db_session.query(m.CrmActivity).filter_by(
            kind=m.CrmActivityKind.MEETING_COMPLETED).one()
        assert activity.meta_json["meeting_id"] == str(meeting.id)

        notes = db_session.query(m.CrmNote).all()
        assert any(n.body.startswith("Meeting summary (AI):") for n in notes)

    def test_only_OUR_commitments_become_tasks(
        self, db_session, meeting, lead, fake_claude
    ):
        """An action item the client owns is information. Turning it into a
        to-do on the user's list is how a task list becomes noise."""
        calendar_tasks.generate_summary_impl(db_session, meeting.id)

        tasks_created = db_session.query(m.CrmActivity).filter_by(
            kind=m.CrmActivityKind.TASK_CREATED).all()
        assert len(tasks_created) == 1
        assert tasks_created[0].to_value == "Send the pricing sheet"

    def test_the_prompt_carries_the_actual_duration(
        self, db_session, meeting, fake_claude
    ):
        """"Booked 60 minutes, ran 22" is a signal about the call. Folding it
        into the scheduled figure would erase it."""
        calendar_tasks.generate_summary_impl(db_session, meeting.id)
        assert "22 minutes" in fake_claude.meeting_prompts[-1]

    def test_a_model_failure_leaves_the_meeting_intact(
        self, db_session, meeting, fake_claude
    ):
        fake_claude.meeting_summary_response = RuntimeError("api down")
        result = calendar_tasks.generate_summary_impl(db_session, meeting.id)
        assert result.startswith("skipped")

        db_session.refresh(meeting)
        assert meeting.summary is None
        assert meeting.raw_notes == "budget approved", (
            "the human's own notes must survive a failed generation"
        )
        assert db_session.query(m.CrmActivity).count() == 0

    def test_nothing_to_summarise_is_not_an_error(
        self, db_session, meeting, fake_claude
    ):
        meeting.transcript = None
        meeting.raw_notes = None
        db_session.commit()
        assert calendar_tasks.generate_summary_impl(
            db_session, meeting.id).startswith("skipped")
        assert fake_claude.meeting_prompts == []

    def test_a_meeting_with_no_lead_still_summarises(
        self, db_session, meeting, fake_claude
    ):
        meeting.lead_id = None
        db_session.commit()
        assert calendar_tasks.generate_summary_impl(
            db_session, meeting.id) == "ok"
        assert db_session.query(m.CrmActivity).count() == 0


# --------------------------------------------------------------------------
# The CRM handlers, directly
# --------------------------------------------------------------------------


class TestCrmHandlers:
    def test_an_action_item_sets_next_action_at(self, db_session, lead):
        due = (datetime.now(UTC) + timedelta(days=3)).date().isoformat()
        crm_events.on_action_item_created(
            db_session, lead.id,
            {"text": "Send the deck", "owner": "us", "due": due},
        )
        db_session.commit()

        meta = db_session.query(m.CrmLeadMeta).filter_by(lead_id=lead.id).one()
        assert meta.next_action_at is not None
        assert meta.next_action_at.date().isoformat() == due

    def test_it_never_pushes_an_earlier_task_out(self, db_session, lead):
        """A summary generated after a call must not move a reminder the user
        set for tomorrow morning."""
        from app.services.crm_service import get_or_create_meta

        tomorrow = datetime.now(UTC) + timedelta(days=1)
        meta = get_or_create_meta(db_session, lead)
        meta.next_action_at = tomorrow
        db_session.commit()

        later = (datetime.now(UTC) + timedelta(days=10)).date().isoformat()
        crm_events.on_action_item_created(
            db_session, lead.id,
            {"text": "Later thing", "owner": "us", "due": later},
        )
        db_session.commit()

        db_session.refresh(meta)
        assert meta.next_action_at.replace(tzinfo=None) == \
            tomorrow.replace(tzinfo=None)

    def test_an_unparseable_due_date_is_skipped_not_fatal(
        self, db_session, lead
    ):
        """The value comes from a model's JSON. A malformed date is a reason
        to skip the reminder, not to fail the whole summary write."""
        activity = crm_events.on_action_item_created(
            db_session, lead.id,
            {"text": "Something", "owner": "us", "due": "next Tuesday-ish"},
        )
        db_session.commit()
        assert activity is not None
        assert db_session.query(m.CrmLeadMeta).count() == 0

    def test_an_empty_action_item_writes_nothing(self, db_session, lead):
        assert crm_events.on_action_item_created(
            db_session, lead.id, {"text": "   "}) is None
        db_session.commit()
        assert db_session.query(m.CrmNote).count() == 0

    def test_the_handlers_do_not_commit(self, db_session, lead):
        """Every one is called inside a transaction the caller owns.
        Committing here would split that work in two and leave a booking that
        half-happened if the second half failed."""
        crm_events.on_booking_created(db_session, lead.id, uuid.uuid4())
        assert db_session.in_transaction()
        db_session.rollback()
        assert db_session.query(m.CrmActivity).count() == 0

    def test_no_crm_handler_writes_to_outcomes(self, db_session, lead):
        """Rule from migration 0019, still true. `outcomes` is the learning
        loop's log; the CRM's audit trail is a different table on purpose."""
        crm_events.on_booking_created(db_session, lead.id, uuid.uuid4())
        crm_events.on_meeting_completed(db_session, lead.id, uuid.uuid4(),
                                        summary="x")
        crm_events.on_action_item_created(db_session, lead.id,
                                          {"text": "y", "owner": "us"})
        db_session.commit()
        assert db_session.query(m.Outcome).count() == 0


# --------------------------------------------------------------------------
# The stale-meeting sweep
# --------------------------------------------------------------------------


class TestStaleMeetings:
    def test_a_started_meeting_nobody_ended_is_completed(
        self, db_session, test_user
    ):
        """Left in_progress it keeps blocking calendar slots and keeps its
        lead's enrollment paused, forever."""
        start = datetime.now(UTC) - timedelta(hours=12)
        row = m.Meeting(host_user_id=test_user.id,
                        platform=m.MeetingPlatform.CUSTOM,
                        start_at=start, end_at=start + timedelta(minutes=30),
                        actual_start_at=start,
                        status=m.MeetingStatus.IN_PROGRESS)
        db_session.add(row)
        db_session.commit()

        assert calendar_tasks.close_stale_meetings_impl(db_session) == 1
        db_session.refresh(row)
        assert row.status is m.MeetingStatus.COMPLETED
        assert row.actual_end_at is not None

    def test_a_meeting_nobody_started_becomes_a_no_show(
        self, db_session, test_user, booking
    ):
        """Recording it as completed would put a call that did not happen into
        the conversion numbers."""
        start = datetime.now(UTC) - timedelta(hours=12)
        booking.start_at = start
        booking.end_at = start + timedelta(minutes=30)
        db_session.commit()

        row = m.Meeting(booking_id=booking.id, host_user_id=test_user.id,
                        platform=m.MeetingPlatform.CUSTOM,
                        start_at=start, end_at=start + timedelta(minutes=30),
                        status=m.MeetingStatus.SCHEDULED)
        db_session.add(row)
        db_session.commit()

        calendar_tasks.close_stale_meetings_impl(db_session)
        db_session.refresh(row)
        db_session.refresh(booking)
        assert row.status is m.MeetingStatus.CANCELLED
        assert booking.status is m.BookingStatus.NO_SHOW
        assert booking.slot_key is None, (
            "a no-show must stop blocking the host's calendar"
        )

    def test_a_meeting_still_inside_the_grace_period_is_left_alone(
        self, db_session, test_user
    ):
        start = datetime.now(UTC) - timedelta(minutes=30)
        row = m.Meeting(host_user_id=test_user.id,
                        platform=m.MeetingPlatform.CUSTOM,
                        start_at=start, end_at=start + timedelta(minutes=30),
                        status=m.MeetingStatus.IN_PROGRESS,
                        actual_start_at=start)
        db_session.add(row)
        db_session.commit()

        assert calendar_tasks.close_stale_meetings_impl(db_session) == 0
