"""M4 tests — unified cross-channel stop conditions (Chunk 4, item 4).

A reply, unsubscribe, or booking on EITHER channel stops EVERYTHING —
the engine stops enrollments, not channels.
"""

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import sequence_engine as engine
from app.services import whatsapp_optin as optin_svc
from app.workers.outreach_tasks import route_whatsapp_inbound_impl
from tests.conftest import NOW


@pytest.fixture()
def dual_enrollments(db_session, verified_strategy, wa_lead, approved_template):
    """The same lead enrolled in an ACTIVE email sequence AND an ACTIVE
    WhatsApp sequence, each with a pending scheduled message."""
    out = {}
    for name, channel in (("email", m.ChannelType.EMAIL),
                          ("whatsapp", m.ChannelType.WHATSAPP)):
        seq = m.Sequence(strategy_id=verified_strategy.id, channel=channel,
                         name=name, status=m.SequenceStatus.ACTIVE)
        db_session.add(seq)
        db_session.flush()
        kwargs = {}
        if channel is m.ChannelType.WHATSAPP:
            kwargs = dict(whatsapp_kind=m.WhatsAppStepKind.TEMPLATE,
                          whatsapp_template_id=approved_template.id,
                          variable_mapping_json={"1": "lead.first_name",
                                                 "2": "brief: x"})
        db_session.add(m.SequenceStep(sequence_id=seq.id, step_no=1,
                                      template="s1", delay_days=0, **kwargs))
        enr = m.SequenceEnrollment(sequence_id=seq.id, lead_id=wa_lead.id,
                                   status=m.EnrollmentStatus.ACTIVE)
        db_session.add(enr)
        db_session.flush()
        msg = m.Message(sequence_id=seq.id, lead_id=wa_lead.id,
                        channel=channel, step_no=1, template="s1",
                        status=m.MessageStatus.SCHEDULED, scheduled_at=NOW,
                        **({"whatsapp_kind": m.WhatsAppStepKind.TEMPLATE,
                            "whatsapp_template_id": approved_template.id}
                           if channel is m.ChannelType.WHATSAPP else {}))
        db_session.add(msg)
        out[name] = (seq, enr, msg)
    db_session.commit()
    return out


def _statuses(db, dual):
    for pair in dual.values():
        db.refresh(pair[1])
    return {name: pair[1].status for name, pair in dual.items()}


class TestCrossChannelStops:
    def test_whatsapp_reply_stops_pending_email_steps(
            self, db_session, fake_claude, wa_lead, dual_enrollments,
            fake_channel):
        reply = m.InboundReply(lead_id=wa_lead.id, channel="whatsapp",
                               from_address=wa_lead.phone,
                               body="yes, tell me more")
        db_session.add(reply)
        db_session.commit()
        fake_claude.default_reply_class = "interested"
        route_whatsapp_inbound_impl(db_session, wa_lead, reply)

        statuses = _statuses(db_session, dual_enrollments)
        assert statuses["email"] is m.EnrollmentStatus.STOPPED
        assert statuses["whatsapp"] is m.EnrollmentStatus.STOPPED
        # the pending EMAIL message was CANCELLED the moment the
        # enrollment stopped (stop_enrollment cancels pending rows), and
        # the send task refuses it either way — nothing transmits.
        from app.workers.outreach_tasks import send_message_impl
        email_msg = dual_enrollments["email"][2]
        db_session.refresh(email_msg)
        assert email_msg.status is m.MessageStatus.CANCELLED
        assert send_message_impl(db_session, email_msg.id,
                                 channel=fake_channel,
                                 now=NOW) == "skipped_cancelled"
        assert fake_channel.sent == []

    def test_email_unsubscribe_suppresses_whatsapp_sends(
            self, db_session, fake_claude, wa_lead, dual_enrollments,
            fake_channel):
        # the lead clicks the email unsubscribe link
        engine.unsubscribe_lead(db_session, wa_lead, source="link")
        statuses = _statuses(db_session, dual_enrollments)
        assert statuses["whatsapp"] is m.EnrollmentStatus.STOPPED
        # phone suppressed too — the pending WhatsApp send is cancelled
        assert db_session.execute(
            select(m.SuppressionEntry).where(
                m.SuppressionEntry.phone == wa_lead.phone)
        ).scalars().first() is not None
        from app.workers.outreach_tasks import send_message_impl
        wa_msg = dual_enrollments["whatsapp"][2]
        db_session.refresh(wa_msg)
        assert wa_msg.status is m.MessageStatus.CANCELLED
        assert send_message_impl(db_session, wa_msg.id, channel=fake_channel,
                                 now=NOW) == "skipped_cancelled"
        assert fake_channel.sent == []

    def test_inbound_stop_suppresses_both_and_writes_audit_row(
            self, db_session, fake_claude, client, wa_lead, dual_enrollments):
        from tests.conftest import wa_signed_post
        delivery = {"entry": [{"changes": [{"field": "messages", "value": {
            "metadata": {"phone_number_id": "5550001"},
            "messages": [{"id": "wamid.STOP1", "from": "923001234567",
                          "timestamp": "1754900000", "type": "text",
                          "text": {"body": "STOP"}}],
        }}]}]}
        resp = wa_signed_post(client, delivery)
        assert resp.status_code == 200

        # suppression on BOTH identifiers
        assert db_session.execute(select(m.SuppressionEntry).where(
            m.SuppressionEntry.phone == wa_lead.phone)).scalars().first()
        assert db_session.execute(select(m.SuppressionEntry).where(
            m.SuppressionEntry.email == wa_lead.email)).scalars().first()
        # the opted_out AUDIT row exists (append-only trail)
        last = optin_svc.latest_row(db_session, wa_lead.id)
        assert last.status is m.OptInStatus.OPTED_OUT
        assert "wamid.STOP1" in (last.evidence or "")
        # every enrollment stopped
        statuses = _statuses(db_session, dual_enrollments)
        assert set(statuses.values()) == {m.EnrollmentStatus.STOPPED}

    def test_calendly_booking_stops_both_channels(
            self, db_session, fake_claude, client, wa_lead, dual_enrollments,
            monkeypatch):
        import app.api.webhooks as calendly_hooks
        monkeypatch.setattr(calendly_hooks, "verify_webhook_signature",
                            lambda raw, sig: True)
        monkeypatch.setattr(calendly_hooks, "extract_event_id",
                            lambda payload, raw: "EV-XCH-1")
        # payload.tracking carries the owning tenant - webhooks.py resolves the
        # account from it and quarantines a booking that has none.
        from app.integrations.calendly import TENANT_TRACKING_PARAM
        from app.services.notifications import owner_of_lead

        resp = client.post("/webhooks/calendly",
                           json={"event": "invitee.created",
                                 "payload": {
                                     "email": wa_lead.email,
                                     "tracking": {TENANT_TRACKING_PARAM: str(
                                         owner_of_lead(db_session, wa_lead))},
                                 }})
        assert resp.status_code == 200
        statuses = _statuses(db_session, dual_enrollments)
        assert set(statuses.values()) == {m.EnrollmentStatus.STOPPED}
        db_session.refresh(wa_lead)
        assert wa_lead.status is m.LeadStatus.MEETING_BOOKED
