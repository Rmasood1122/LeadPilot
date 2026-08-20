"""Reply detection — classification routing, OOO pause, outcomes, no auto-reply."""

from datetime import timedelta

from sqlalchemy import select

from app.db import models as m
from app.integrations.outreach_base import InboundMessage
from app.services import sequence_engine as engine
from app.workers.outreach_tasks import (
    poll_account_replies_impl,
    route_inbound_impl,
    send_message_impl,
)
from tests.conftest import NOW


def _sent_first_message(db, sequence, lead, channel):
    msg = db.execute(select(m.Message).where(m.Message.lead_id == lead.id)).scalar_one()
    assert send_message_impl(db, msg.id, channel=channel, now=NOW) == "sent"
    return msg


def _inbound(lead, body, thread_ref=None, subject="Re: hello"):
    return InboundMessage(
        provider_message_id="in1", thread_ref=thread_ref,
        from_address=lead.email, to_address="sender@leadpilot.dev",
        subject=subject, body=body, received_at=NOW,
    )


def _enrollment(db, lead):
    return db.execute(select(m.SequenceEnrollment).where(
        m.SequenceEnrollment.lead_id == lead.id)).scalar_one()


class TestClassificationRouting:
    def test_interested_stops_and_records(self, db_session, enrolled, verified_leads,
                                          fake_channel, fake_claude, gmail_account):
        lead = verified_leads[0]
        msg = _sent_first_message(db_session, enrolled, lead, fake_channel)
        fake_claude.reply_verdicts["sounds great"] = "interested"

        out = route_inbound_impl(db_session, _inbound(lead, "sounds great, tell me more",
                                                      thread_ref=msg.thread_ref), gmail_account)
        assert out == "interested"
        assert lead.status is m.LeadStatus.REPLIED
        assert _enrollment(db_session, lead).status is m.EnrollmentStatus.STOPPED
        reply = db_session.execute(select(m.InboundReply)).scalar_one()
        assert reply.classification == "interested" and reply.lead_id == lead.id
        assert reply.message_id == msg.id, "matched via thread_ref"
        outcomes = {o.event for o in db_session.execute(
            select(m.Outcome).where(m.Outcome.lead_id == lead.id)).scalars()}
        assert m.OutcomeEvent.REPLIED in outcomes and m.OutcomeEvent.SENT in outcomes

    def test_unsubscribe_request_is_instant_suppression(self, db_session, enrolled,
                                                        verified_leads, fake_channel,
                                                        fake_claude, gmail_account):
        lead = verified_leads[1]
        _sent_first_message(db_session, enrolled, lead, fake_channel)
        fake_claude.reply_verdicts["stop emailing me"] = "unsubscribe_request"

        out = route_inbound_impl(db_session, _inbound(lead, "stop emailing me please"),
                                 gmail_account)
        assert out == "unsubscribe_request"
        assert any(s.email == lead.email for s in
                   db_session.execute(select(m.SuppressionEntry)).scalars())
        assert _enrollment(db_session, lead).status is m.EnrollmentStatus.STOPPED
        events = {o.event for o in db_session.execute(
            select(m.Outcome).where(m.Outcome.lead_id == lead.id)).scalars()}
        assert m.OutcomeEvent.UNSUBSCRIBED in events

    def test_bounce_reply_records_and_checks_rate(self, db_session, enrolled,
                                                  verified_leads, fake_channel,
                                                  fake_claude, gmail_account):
        lead = verified_leads[2]
        msg = _sent_first_message(db_session, enrolled, lead, fake_channel)
        fake_claude.reply_verdicts["address not found"] = "bounce"

        out = route_inbound_impl(
            db_session,
            InboundMessage(provider_message_id="b1", thread_ref=msg.thread_ref,
                           from_address="mailer-daemon@googlemail.com", to_address=None,
                           subject="Delivery Status Notification",
                           body="address not found", received_at=NOW),
            gmail_account)
        assert out == "bounce"
        assert lead.status is m.LeadStatus.DROPPED
        assert msg.status is m.MessageStatus.BOUNCED
        events = [o.event for o in db_session.execute(
            select(m.Outcome).where(m.Outcome.lead_id == lead.id)).scalars()]
        assert m.OutcomeEvent.BOUNCED in events

    def test_out_of_office_pauses_and_resumes(self, db_session, enrolled, verified_leads,
                                              fake_channel, fake_claude, gmail_account):
        lead = verified_leads[0]
        _sent_first_message(db_session, enrolled, lead, fake_channel)
        fake_claude.reply_verdicts["annual leave"] = "out_of_office"

        out = route_inbound_impl(db_session,
                                 _inbound(lead, "I am on annual leave until next month"),
                                 gmail_account)
        assert out == "out_of_office"
        e = _enrollment(db_session, lead)
        assert e.status is m.EnrollmentStatus.PAUSED, "pauses, does not stop"
        assert e.paused_until is not None
        followup = db_session.execute(select(m.Message).where(
            m.Message.lead_id == lead.id, m.Message.step_no == 2)).scalar_one()
        assert followup.scheduled_at >= e.paused_until, "pending message rescheduled"

        # After paused_until passes, the dispatcher resumes it.
        engine.resume_due_enrollments(db_session, now=e.paused_until + timedelta(hours=1))
        assert e.status is m.EnrollmentStatus.ACTIVE

    def test_no_auto_reply_to_humans(self, db_session, enrolled, verified_leads,
                                     fake_channel, gmail_account):
        lead = verified_leads[0]
        _sent_first_message(db_session, enrolled, lead, fake_channel)
        sends_before = len(fake_channel.sent)
        route_inbound_impl(db_session, _inbound(lead, "interesting, what does it cost?"),
                           gmail_account)
        assert len(fake_channel.sent) == sends_before, "M3 never auto-replies"

    def test_unmatched_inbound_is_stored_not_dropped(self, db_session, enrolled,
                                                     gmail_account):
        stranger = InboundMessage(provider_message_id="s1", thread_ref=None,
                                  from_address="stranger@nowhere.com", to_address=None,
                                  subject="hi", body="who is this?", received_at=NOW)
        out = route_inbound_impl(db_session, stranger, gmail_account)
        assert out.startswith("unmatched_")
        reply = db_session.execute(select(m.InboundReply)).scalar_one()
        assert reply.lead_id is None and reply.from_address == "stranger@nowhere.com"


class TestPolling:
    def test_poll_routes_all_and_advances_cursor(self, db_session, enrolled,
                                                 verified_leads, fake_channel,
                                                 fake_claude, gmail_account):
        lead = verified_leads[0]
        _sent_first_message(db_session, enrolled, lead, fake_channel)
        fake_channel.inbox = [_inbound(lead, "sounds great")]
        handled = poll_account_replies_impl(db_session, gmail_account,
                                            channel=fake_channel, now=NOW)
        assert handled == 1
        assert gmail_account.last_poll_at == NOW
