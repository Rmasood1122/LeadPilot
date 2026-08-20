"""Sequence engine — hard stops, idempotent sending, step scheduling."""

from datetime import timedelta

from sqlalchemy import select

from app.db import models as m
from app.services import sequence_engine as engine
from app.workers.outreach_tasks import dispatch_due_messages_impl, send_message_impl
from tests.conftest import NOW


def pending(db, sequence):
    return db.execute(
        select(m.Message).where(m.Message.sequence_id == sequence.id,
                                m.Message.status == m.MessageStatus.SCHEDULED)
    ).scalars().all()


def enrollment_of(db, sequence, lead):
    return db.execute(
        select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.sequence_id == sequence.id,
            m.SequenceEnrollment.lead_id == lead.id)
    ).scalar_one()


class TestEnrollment:
    def test_enroll_schedules_step1_per_lead(self, db_session, enrolled):
        msgs = pending(db_session, enrolled)
        assert len(msgs) == 3
        assert all(msg.step_no == 1 for msg in msgs)
        assert all(msg.scheduled_at is not None for msg in msgs)

    def test_enroll_is_idempotent(self, db_session, enrolled, fake_claude):
        assert engine.enroll_leads(db_session, enrolled, now=NOW) == 0
        assert len(pending(db_session, enrolled)) == 3

    def test_suppressed_leads_not_enrolled(self, db_session, fake_claude,
                                           email_sequence, verified_leads, gmail_account):
        db_session.add(m.SuppressionEntry(email=verified_leads[0].email,
                                          reason="unsubscribed"))
        db_session.commit()
        assert engine.enroll_leads(db_session, email_sequence, now=NOW) == 2


class TestHardStops:
    """replied / unsubscribed / bounced / meeting_booked — a stopped
    enrollment can NEVER send again."""

    def _stopped_never_sends(self, db, sequence, lead, fake_channel):
        enrollment = enrollment_of(db, sequence, lead)
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        msg = db.execute(select(m.Message).where(m.Message.lead_id == lead.id)).scalars().first()
        assert msg.status is m.MessageStatus.CANCELLED
        # Even forcing the message back to scheduled cannot send it:
        msg.status = m.MessageStatus.SCHEDULED
        db.commit()
        out = send_message_impl(db, msg.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_stopped"
        assert fake_channel.sent == []

    def test_stop_on_reply(self, db_session, enrolled, verified_leads, fake_channel):
        e = enrollment_of(db_session, enrolled, verified_leads[0])
        engine.stop_enrollment(db_session, e, reason="replied_interested")
        self._stopped_never_sends(db_session, enrolled, verified_leads[0], fake_channel)

    def test_stop_on_unsubscribe_adds_suppression(self, db_session, enrolled,
                                                  verified_leads, fake_channel):
        lead = verified_leads[1]
        engine.unsubscribe_lead(db_session, lead, source="link")
        entries = db_session.execute(select(m.SuppressionEntry)).scalars().all()
        assert any(s.email == lead.email for s in entries)
        outcomes = db_session.execute(
            select(m.Outcome).where(m.Outcome.lead_id == lead.id)).scalars().all()
        assert any(o.event is m.OutcomeEvent.UNSUBSCRIBED for o in outcomes)
        self._stopped_never_sends(db_session, enrolled, lead, fake_channel)

    def test_stop_on_bounce_drops_lead(self, db_session, enrolled, verified_leads, fake_channel):
        lead = verified_leads[2]
        engine.record_bounce(db_session, lead)
        assert lead.status is m.LeadStatus.DROPPED
        self._stopped_never_sends(db_session, enrolled, lead, fake_channel)

    def test_stop_on_meeting_booked(self, db_session, enrolled, verified_leads, fake_channel):
        e = enrollment_of(db_session, enrolled, verified_leads[0])
        engine.stop_enrollment(db_session, e, reason="meeting_booked")
        self._stopped_never_sends(db_session, enrolled, verified_leads[0], fake_channel)


class TestIdempotentSending:
    def test_happy_send_transitions_and_outcome(self, db_session, enrolled,
                                                verified_leads, fake_channel):
        msg = pending(db_session, enrolled)[0]
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"
        assert msg.status is m.MessageStatus.SENT
        assert msg.provider_message_id == "pm1" and msg.thread_ref == "th1"
        assert msg.body and "rendered body" in msg.body, "body persisted"
        lead = db_session.get(m.Lead, msg.lead_id)
        assert lead.status is m.LeadStatus.CONTACTED
        outcome = db_session.execute(
            select(m.Outcome).where(m.Outcome.message_id == msg.id)).scalar_one()
        assert outcome.event is m.OutcomeEvent.SENT

    def test_retry_on_sent_message_does_not_double_send(self, db_session, enrolled,
                                                        fake_channel):
        msg = pending(db_session, enrolled)[0]
        send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "already_sent"
        assert len(fake_channel.sent) == 1

    def test_retry_on_sending_message_does_not_double_send(self, db_session, enrolled,
                                                           fake_channel):
        msg = pending(db_session, enrolled)[0]
        msg.status = m.MessageStatus.SENDING  # a crashed in-flight attempt
        db_session.commit()
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "in_flight_needs_review"
        assert fake_channel.sent == []

    def test_transient_failure_returns_to_scheduled(self, db_session, enrolled, fake_channel):
        from app.integrations.outreach_base import SendResult
        fake_channel.result_queue = [SendResult(ok=False, error="503", permanent_failure=False)]
        msg = pending(db_session, enrolled)[0]
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "failed_transient"
        assert msg.status is m.MessageStatus.SCHEDULED, "retryable, never lost"

    def test_permanent_failure_marks_failed(self, db_session, enrolled, fake_channel):
        from app.integrations.outreach_base import SendResult
        fake_channel.result_queue = [SendResult(ok=False, error="400", permanent_failure=True)]
        msg = pending(db_session, enrolled)[0]
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "failed_permanent"
        assert msg.status is m.MessageStatus.FAILED


class TestFollowUps:
    def test_next_step_scheduled_with_delay_and_thread(self, db_session, enrolled,
                                                       verified_leads, fake_channel):
        lead = verified_leads[0]
        msg1 = db_session.execute(
            select(m.Message).where(m.Message.lead_id == lead.id)).scalar_one()
        send_message_impl(db_session, msg1.id, channel=fake_channel, now=NOW)

        msg2 = db_session.execute(
            select(m.Message).where(m.Message.lead_id == lead.id,
                                    m.Message.step_no == 2)).scalar_one()
        assert msg2.status is m.MessageStatus.SCHEDULED
        when = msg2.scheduled_at
        if when.tzinfo is None:  # SQLite round-trips as naive UTC
            from datetime import timezone as _tz
            when = when.replace(tzinfo=_tz.utc)
        assert when >= NOW + timedelta(days=3)  # step-2 delay

        # follow-up threads onto the first send
        msg2.scheduled_at = NOW
        db_session.commit()
        send_message_impl(db_session, msg2.id, channel=fake_channel, now=NOW)
        assert fake_channel.sent[1].thread_ref == "th1"

    def test_completion_after_last_step(self, db_session, enrolled, verified_leads, fake_channel):
        lead = verified_leads[0]
        for step in (1, 2, 3):
            msg = db_session.execute(
                select(m.Message).where(m.Message.lead_id == lead.id,
                                        m.Message.step_no == step)).scalar_one()
            msg.scheduled_at = NOW
            db_session.commit()
            assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"
        e = enrollment_of(db_session, enrolled, lead)
        assert e.status is m.EnrollmentStatus.COMPLETED
        assert len(fake_channel.sent) == 3


class TestDispatcher:
    def test_dispatch_enqueues_due_messages_only(self, db_session, enrolled):
        msgs = pending(db_session, enrolled)
        msgs[0].scheduled_at = NOW - timedelta(minutes=5)
        msgs[1].scheduled_at = NOW + timedelta(days=1)   # not due
        msgs[2].scheduled_at = NOW - timedelta(minutes=1)
        db_session.commit()
        queued: list[str] = []
        out = dispatch_due_messages_impl(db_session, now=NOW, enqueue=queued.append)
        assert set(out) == {str(msgs[0].id), str(msgs[2].id)}

    def test_dispatch_skips_paused_campaigns(self, db_session, enrolled, verified_strategy):
        verified_strategy.campaign_state = engine.CAMPAIGN_PAUSED_BOUNCE
        db_session.commit()
        queued: list[str] = []
        dispatch_due_messages_impl(db_session, now=NOW, enqueue=queued.append)
        assert queued == []
