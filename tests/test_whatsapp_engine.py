"""M4 tests — engine rules on the WhatsApp send path (Chunk 4, items 3, 5, 7).

Skip-and-continue semantics, all-skipped flagging, per-channel daily cap
(defers, never drops), business-hours scheduling, and idempotent
scheduled -> sending -> sent transitions.
"""

from datetime import timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.db import models as m
from app.services import sequence_engine as engine
from app.workers.outreach_tasks import send_message_impl
from tests.conftest import NOW


def _schedule_step(db, sequence, lead, step_no, when=NOW):
    step = db.execute(
        select(m.SequenceStep).where(m.SequenceStep.sequence_id == sequence.id,
                                     m.SequenceStep.step_no == step_no)
    ).scalar_one()
    enrollment = db.execute(
        select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.sequence_id == sequence.id,
            m.SequenceEnrollment.lead_id == lead.id)
    ).scalar_one_or_none()
    if enrollment is None:
        enrollment = m.SequenceEnrollment(sequence_id=sequence.id,
                                          lead_id=lead.id,
                                          status=m.EnrollmentStatus.ACTIVE)
        db.add(enrollment)
        db.commit()
    msg = engine._schedule_step_message(db, sequence, enrollment, lead, step,
                                        base_time=when)
    msg.scheduled_at = when
    db.commit()
    return msg, enrollment


class TestSkipSemantics:
    def test_no_optin_step_skipped_and_sequence_continues(
            self, db_session, fake_claude, gmail_account, multichannel_sequence,
            wa_lead_no_optin, approved_template, fake_channel):
        # step 2 is the WhatsApp step; the lead has NO opt-in
        msg, enrollment = _schedule_step(db_session, multichannel_sequence,
                                         wa_lead_no_optin, step_no=2)
        result = send_message_impl(db_session, msg.id, channel=fake_channel,
                                   now=NOW)
        db_session.refresh(msg)
        assert result == "skipped_no_optin"
        assert msg.status is m.MessageStatus.SKIPPED
        assert msg.error == "skipped_no_optin"
        assert fake_channel.sent == []
        # ...and the sequence CONTINUED: step 3 (email) is now scheduled
        next_msg = db_session.execute(
            select(m.Message).where(m.Message.lead_id == wa_lead_no_optin.id,
                                    m.Message.step_no == 3)
        ).scalar_one()
        assert next_msg.status is m.MessageStatus.SCHEDULED
        assert next_msg.channel is m.ChannelType.EMAIL
        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.ACTIVE

    def test_all_whatsapp_no_optin_completes_all_skipped_and_flags(
            self, db_session, fake_claude, verified_strategy,
            wa_lead_no_optin, approved_template, fake_channel):
        seq = m.Sequence(strategy_id=verified_strategy.id,
                         channel=m.ChannelType.WHATSAPP, name="wa-only",
                         status=m.SequenceStatus.ACTIVE)
        db_session.add(seq)
        db_session.flush()
        for n in (1, 2):
            db_session.add(m.SequenceStep(
                sequence_id=seq.id, step_no=n, template=f"s{n}", delay_days=0,
                whatsapp_kind=m.WhatsAppStepKind.TEMPLATE,
                whatsapp_template_id=approved_template.id,
                variable_mapping_json={"1": "lead.first_name", "2": "brief: x"}))
        db_session.commit()

        msg1, enrollment = _schedule_step(db_session, seq, wa_lead_no_optin, 1)
        assert send_message_impl(db_session, msg1.id, channel=fake_channel,
                                 now=NOW) == "skipped_no_optin"
        msg2 = db_session.execute(
            select(m.Message).where(m.Message.sequence_id == seq.id,
                                    m.Message.step_no == 2)
        ).scalar_one()
        msg2.scheduled_at = NOW
        db_session.commit()
        assert send_message_impl(db_session, msg2.id, channel=fake_channel,
                                 now=NOW) == "skipped_no_optin"

        db_session.refresh(enrollment)
        assert enrollment.status is m.EnrollmentStatus.COMPLETED
        # flagged for user attention — zero sends happened
        assert enrollment.stop_reason == "completed_all_skipped_needs_attention"
        assert fake_channel.sent == []


class TestCapsAndScheduling:
    def test_whatsapp_daily_cap_defers_never_drops(
            self, db_session, fake_claude, multichannel_sequence, wa_lead,
            approved_template, fake_channel, monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_daily_cap", 1)
        monkeypatch.setattr(settings, "whatsapp_warmup_start_sends", 1)
        msg1, _ = _schedule_step(db_session, multichannel_sequence, wa_lead, 2)
        assert send_message_impl(db_session, msg1.id, channel=fake_channel,
                                 now=NOW) == "sent"
        # a second WhatsApp message today: over the cap
        msg2 = m.Message(sequence_id=multichannel_sequence.id,
                         lead_id=wa_lead.id, channel=m.ChannelType.WHATSAPP,
                         step_no=2, template="wa follow",
                         whatsapp_kind=m.WhatsAppStepKind.TEMPLATE,
                         whatsapp_template_id=approved_template.id,
                         status=m.MessageStatus.SCHEDULED, scheduled_at=NOW)
        db_session.add(msg2)
        db_session.commit()
        result = send_message_impl(db_session, msg2.id, channel=fake_channel,
                                   now=NOW)
        db_session.refresh(msg2)
        assert result == "deferred_cap"
        assert msg2.status is m.MessageStatus.SCHEDULED       # never dropped
        assert msg2.scheduled_at.replace(tzinfo=timezone.utc) > NOW  # tomorrow
        assert len(fake_channel.sent) == 1

    def test_whatsapp_warmup_ramp(self, db_session, fake_claude,
                                  monkeypatch):
        monkeypatch.setattr(settings, "whatsapp_daily_cap", 100)
        monkeypatch.setattr(settings, "whatsapp_warmup_start_sends", 10)
        monkeypatch.setattr(settings, "whatsapp_warmup_daily_increment", 10)
        # no sends yet -> the starting allowance
        assert engine.whatsapp_daily_allowance(db_session, NOW.date()) == 10

    def test_business_hours_respected_per_lead_timezone(
            self, db_session, fake_claude, multichannel_sequence, wa_lead,
            approved_template, fake_channel):
        # lead in Karachi (UTC+5): 18:00 UTC = 23:00 local -> outside 9-17
        wa_lead.enrichment_json = {"timezone": "Asia/Karachi"}
        msg, _ = _schedule_step(db_session, multichannel_sequence, wa_lead, 2)
        late = NOW.replace(hour=18)
        result = send_message_impl(db_session, msg.id, channel=fake_channel,
                                   now=late)
        db_session.refresh(msg)
        assert result == "deferred_window"
        assert msg.status is m.MessageStatus.SCHEDULED
        assert fake_channel.sent == []


class TestIdempotency:
    def test_sent_message_never_resent(self, db_session, fake_claude,
                                       multichannel_sequence, wa_lead,
                                       approved_template, fake_channel):
        msg, _ = _schedule_step(db_session, multichannel_sequence, wa_lead, 2)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "sent"
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == "already_sent"
        assert len(fake_channel.sent) == 1

    def test_celery_retry_on_sending_does_not_double_send(
            self, db_session, fake_claude, multichannel_sequence, wa_lead,
            approved_template, fake_channel):
        """A message claimed by a crashed attempt is flagged, not resent."""
        msg, _ = _schedule_step(db_session, multichannel_sequence, wa_lead, 2)
        msg.status = m.MessageStatus.SENDING  # crashed in-flight attempt
        db_session.commit()
        result = send_message_impl(db_session, msg.id, channel=fake_channel,
                                   now=NOW)
        assert result == "in_flight_needs_review"
        assert fake_channel.sent == []

    def test_rendered_body_persisted_before_transmit(
            self, db_session, fake_claude, multichannel_sequence, wa_lead,
            approved_template, fake_channel):
        msg, _ = _schedule_step(db_session, multichannel_sequence, wa_lead, 2)
        send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        db_session.refresh(msg)
        # variable values from FakeClaude/lead: preview rendered into body
        assert "{{" not in (msg.body or "{{")
        assert "Reply STOP to opt out" in msg.body
        sent = fake_channel.sent[0]
        assert sent.metadata["template_name"] == "intro_v1"
        params = sent.metadata["components"][0]["parameters"]
        assert [p["type"] for p in params] == ["text", "text"]


class TestTemplateApprovalAtSendTime:
    def test_template_rejected_after_scheduling_parks_needs_template(
            self, db_session, fake_claude, multichannel_sequence, wa_lead,
            approved_template, fake_channel):
        msg, _ = _schedule_step(db_session, multichannel_sequence, wa_lead, 2)
        approved_template.status = m.WhatsAppTemplateStatus.REJECTED
        db_session.commit()
        result = send_message_impl(db_session, msg.id, channel=fake_channel,
                                   now=NOW)
        db_session.refresh(msg)
        assert result == "needs_template_not_approved"
        assert msg.status is m.MessageStatus.NEEDS_TEMPLATE
        assert fake_channel.sent == []
