"""Compliance core — the tests that must never go red."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.db import models as m
from app.services import sequence_engine as engine
from app.workers.outreach_tasks import send_message_impl
from tests.conftest import NOW


def first_pending(db, sequence):
    return db.execute(
        select(m.Message).where(m.Message.sequence_id == sequence.id,
                                m.Message.status == m.MessageStatus.SCHEDULED)
        .order_by(m.Message.created_at)
    ).scalars().first()


class TestSendTimeSuppression:
    def test_suppressed_after_scheduling_is_never_sent(self, db_session, enrolled,
                                                       verified_leads, fake_channel):
        """The scenario the law cares about: unsubscribe arrives AFTER the
        message was scheduled. The send task re-checks and cancels."""
        lead = verified_leads[0]
        msg = db_session.execute(
            select(m.Message).where(m.Message.lead_id == lead.id)).scalar_one()
        db_session.add(m.SuppressionEntry(email=lead.email, reason="unsubscribed"))
        db_session.commit()

        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_suppressed"
        assert msg.status is m.MessageStatus.CANCELLED
        assert fake_channel.sent == [], "no exceptions, no bypass flag"
        e = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == lead.id)).scalar_one()
        assert e.status is m.EnrollmentStatus.STOPPED


class TestUnsubscribeEndpoint:
    def test_valid_token_suppresses_and_stops(self, leads_client, db_session,
                                              enrolled, verified_leads):
        lead = verified_leads[0]
        token = engine.make_unsubscribe_token(lead.id)
        r = leads_client.get(f"/unsubscribe/{token}")
        assert r.status_code == 200
        assert "unsubscribed" in r.text.lower()
        assert any(s.email == lead.email for s in
                   db_session.execute(select(m.SuppressionEntry)).scalars())
        e = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == lead.id)).scalar_one()
        assert e.status is m.EnrollmentStatus.STOPPED

    def test_one_click_post_works_too(self, leads_client, db_session, enrolled, verified_leads):
        token = engine.make_unsubscribe_token(verified_leads[1].id)
        assert leads_client.post(f"/unsubscribe/{token}").status_code == 200

    def test_invalid_token_rejected_safely(self, leads_client, db_session):
        r = leads_client.get("/unsubscribe/not-a-real-token")
        assert r.status_code == 400
        assert "not valid" in r.text
        assert db_session.execute(select(m.SuppressionEntry)).scalars().all() == []

    def test_headers_and_footer_on_every_rendered_email(self, db_session, enrolled,
                                                        fake_channel):
        msg = first_pending(db_session, enrolled)
        send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        sent = fake_channel.sent[0]
        assert "List-Unsubscribe" in sent.headers
        assert sent.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert "/unsubscribe/" in sent.headers["List-Unsubscribe"]
        assert settings.sender_identity in sent.body       # CAN-SPAM identity
        assert "/unsubscribe/" in sent.body                # visible link
        assert msg.unsubscribe_token, "token persisted with the message"


class TestCapsAndWarmup:
    def test_warmup_ramp_day_by_day(self, gmail_account):
        start = settings.gmail_warmup_start_sends
        inc = settings.gmail_warmup_daily_increment
        cap = settings.gmail_daily_cap
        day0 = gmail_account.created_at.date()
        assert engine.daily_allowance(gmail_account, day0) == start
        assert engine.daily_allowance(gmail_account, day0 + timedelta(days=1)) == start + inc
        assert engine.daily_allowance(gmail_account, day0 + timedelta(days=3)) == start + 3 * inc
        assert engine.daily_allowance(gmail_account, day0 + timedelta(days=365)) == cap

    def test_send_beyond_allowance_is_deferred_not_dropped(
        self, db_session, enrolled, gmail_account, fake_channel
    ):
        # Fresh account: today's allowance = warm-up start (10). Simulate
        # the allowance being fully used.
        gmail_account.created_at = NOW
        db_session.commit()
        lead = db_session.execute(select(m.Lead)).scalars().first()
        for i in range(settings.gmail_warmup_start_sends):
            db_session.add(m.Message(
                sequence_id=enrolled.id, lead_id=lead.id, channel=m.ChannelType.EMAIL,
                step_no=1, template="x", status=m.MessageStatus.SENT,
                sent_at=NOW, sender_ref=str(gmail_account.id)))
        db_session.commit()

        msg = first_pending(db_session, enrolled)
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "deferred_cap"
        assert msg.status is m.MessageStatus.SCHEDULED, "deferred, never dropped"
        assert msg.scheduled_at.date() > NOW.date(), "moved to the next day"
        assert fake_channel.sent == []


class TestSendWindow:
    def test_outside_hours_defers_to_window_start(self, db_session, enrolled, fake_channel):
        msg = first_pending(db_session, enrolled)
        early = NOW.replace(hour=6)  # Tuesday 06:00 — before 09:00 window
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=early)
        assert out == "deferred_window"
        assert msg.scheduled_at == NOW.replace(hour=9)
        assert fake_channel.sent == []

    def test_weekend_skipped_to_monday(self):
        saturday = datetime(2026, 8, 15, 11, 0, tzinfo=timezone.utc)
        slot = engine.next_window_slot(saturday, "UTC")
        assert slot == datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)  # Monday 09:00

    def test_lead_timezone_used_when_present(self, db_session, verified_leads):
        lead = verified_leads[0]
        lead.enrichment_json = {**lead.enrichment_json, "timezone": "America/Chicago"}
        db_session.commit()
        assert engine.lead_timezone(lead) == "America/Chicago"
        # 10:00 UTC on a Tuesday is 05:00 in Chicago — outside the window.
        assert not engine.in_send_window(NOW, engine.lead_timezone(lead))

    def test_invalid_lead_timezone_falls_back(self, db_session, verified_leads):
        lead = verified_leads[1]
        lead.enrichment_json = {**lead.enrichment_json, "timezone": "Mars/Olympus"}
        db_session.commit()
        assert engine.lead_timezone(lead) == settings.send_window_timezone


class TestBounceAutoPause:
    def _sent(self, db, sequence, lead, n, account_id):
        for _ in range(n):
            db.add(m.Message(sequence_id=sequence.id, lead_id=lead.id,
                             channel=m.ChannelType.EMAIL, step_no=1, template="x",
                             status=m.MessageStatus.SENT, sent_at=NOW,
                             sender_ref=account_id))
        db.commit()

    def test_campaign_pauses_above_threshold(self, db_session, enrolled, verified_leads,
                                             verified_strategy, gmail_account):
        # 20 sends, 1 bounce = 5% > 3% -> pause
        self._sent(db_session, enrolled, verified_leads[0], 20, str(gmail_account.id))
        engine.record_bounce(db_session, verified_leads[1])
        assert verified_strategy.campaign_state == engine.CAMPAIGN_PAUSED_BOUNCE
        assert "human review" in verified_strategy.campaign_pause_reason

    def test_no_pause_below_min_sample(self, db_session, enrolled, verified_leads,
                                       verified_strategy, gmail_account):
        # 2 sends, 1 bounce = 50%, but below BOUNCE_MIN_SENDS -> stay active
        self._sent(db_session, enrolled, verified_leads[0], 2, str(gmail_account.id))
        engine.record_bounce(db_session, verified_leads[1])
        assert verified_strategy.campaign_state == engine.CAMPAIGN_ACTIVE

    def test_paused_campaign_blocks_sends(self, db_session, enrolled, verified_strategy,
                                          fake_channel):
        verified_strategy.campaign_state = engine.CAMPAIGN_PAUSED_BOUNCE
        db_session.commit()
        msg = first_pending(db_session, enrolled)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "campaign_paused"
        assert fake_channel.sent == []
