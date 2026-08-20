"""M4 tests — the WhatsApp webhook + outcomes completeness (Chunk 4,
items 5 and 8).

Signature enforcement (fail-closed), per-event idempotency across retried
deliveries, status -> Message/Outcome mapping, inbound handling, and the
assertion M8 depends on: every outcome row carries the correct channel.
"""

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import whatsapp_optin as optin_svc
from tests.conftest import NOW, wa_signed_post


def _status_delivery(wamid, status):
    return {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "5550001"},
        "statuses": [{"id": wamid, "status": status,
                      "timestamp": "1754900000",
                      "errors": [{"title": "Unreachable"}]
                      if status == "failed" else []}],
    }}]}]}


def _inbound_delivery(wamid, from_phone, text):
    return {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "5550001"},
        "messages": [{"id": wamid, "from": from_phone,
                      "timestamp": "1754900000", "type": "text",
                      "text": {"body": text}}],
    }}]}]}


@pytest.fixture()
def sent_wa_message(db_session, verified_strategy, wa_lead, approved_template):
    seq = m.Sequence(strategy_id=verified_strategy.id,
                     channel=m.ChannelType.WHATSAPP, name="wa",
                     status=m.SequenceStatus.ACTIVE)
    db_session.add(seq)
    db_session.flush()
    enr = m.SequenceEnrollment(sequence_id=seq.id, lead_id=wa_lead.id,
                               status=m.EnrollmentStatus.ACTIVE)
    db_session.add(enr)
    msg = m.Message(sequence_id=seq.id, lead_id=wa_lead.id,
                    channel=m.ChannelType.WHATSAPP, step_no=1, template="t",
                    whatsapp_kind=m.WhatsAppStepKind.TEMPLATE,
                    whatsapp_template_id=approved_template.id,
                    provider_message_id="wamid.SENT1",
                    status=m.MessageStatus.SENT, sent_at=NOW)
    db_session.add(msg)
    db_session.commit()
    return msg


class TestSignature:
    def test_invalid_signature_rejected(self, client):
        r = wa_signed_post(client, {"entry": []}, secret="wrong-secret")
        assert r.status_code == 401

    def test_missing_signature_rejected(self, client):
        assert client.post("/webhooks/whatsapp", json={}).status_code == 401

    def test_missing_app_secret_fails_closed(self, client, monkeypatch):
        from app.config import settings
        monkeypatch.setattr(settings, "whatsapp_app_secret", "")
        # even a correctly signed request is rejected: fail-closed, never
        # accept-all
        assert wa_signed_post(client, {"entry": []}, secret="").status_code == 401

    def test_verification_handshake(self, client):
        r = client.get("/webhooks/whatsapp", params={
            "hub.mode": "subscribe", "hub.verify_token": "test-verify-token",
            "hub.challenge": "12321"})
        assert (r.status_code, r.text) == (200, "12321")
        assert client.get("/webhooks/whatsapp", params={
            "hub.mode": "subscribe", "hub.verify_token": "wrong",
            "hub.challenge": "1"}).status_code == 403


class TestIdempotency:
    def test_duplicate_delivery_processed_once(self, client, db_session,
                                               fake_claude, sent_wa_message,
                                               wa_lead):
        delivery = _status_delivery("wamid.SENT1", "read")
        assert wa_signed_post(client, delivery).json()["processed"] == 1
        # Meta retries the exact same delivery:
        second = wa_signed_post(client, delivery).json()
        assert (second["processed"], second["duplicates"]) == (0, 1)
        opened = db_session.execute(select(m.Outcome).where(
            m.Outcome.event == m.OutcomeEvent.OPENED)).scalars().all()
        assert len(opened) == 1  # acted on exactly once

    def test_distinct_statuses_of_one_message_both_process(self, client,
                                                           fake_claude,
                                                           sent_wa_message):
        """'delivered' then 'read' share a wamid — the dedupe key includes
        the status so neither is swallowed."""
        assert wa_signed_post(client, _status_delivery(
            "wamid.SENT1", "delivered")).json()["processed"] == 1
        assert wa_signed_post(client, _status_delivery(
            "wamid.SENT1", "read")).json()["processed"] == 1


class TestStatusEvents:
    def test_read_writes_opened_outcome_with_channel(self, client, db_session,
                                                     fake_claude,
                                                     sent_wa_message, wa_lead):
        wa_signed_post(client, _status_delivery("wamid.SENT1", "read"))
        outcome = db_session.execute(select(m.Outcome).where(
            m.Outcome.event == m.OutcomeEvent.OPENED)).scalars().one()
        assert outcome.channel == "whatsapp"
        assert outcome.message_id == sent_wa_message.id

    def test_failed_runs_bounce_path(self, client, db_session, fake_claude,
                                     sent_wa_message, wa_lead):
        wa_signed_post(client, _status_delivery("wamid.SENT1", "failed"))
        db_session.refresh(sent_wa_message)
        db_session.refresh(wa_lead)
        assert sent_wa_message.status is m.MessageStatus.BOUNCED
        assert "Unreachable" in (sent_wa_message.error or "")
        assert wa_lead.status is m.LeadStatus.DROPPED
        bounce = db_session.execute(select(m.Outcome).where(
            m.Outcome.event == m.OutcomeEvent.BOUNCED)).scalars().one()
        assert bounce.channel == "whatsapp"
        enrollment = db_session.execute(
            select(m.SequenceEnrollment).where(
                m.SequenceEnrollment.lead_id == wa_lead.id)).scalars().one()
        assert enrollment.status is m.EnrollmentStatus.STOPPED

    def test_unknown_wamid_ignored(self, client, fake_claude):
        r = wa_signed_post(client, _status_delivery("wamid.NOBODY", "read"))
        assert r.status_code == 200  # acknowledged, nothing to act on


class TestInboundEvents:
    def test_inbound_sets_window_anchor_and_records_initiation_optin(
            self, client, db_session, fake_claude, wa_lead_no_optin):
        fake_claude.default_reply_class = "question"
        wa_signed_post(client, _inbound_delivery(
            "wamid.IN1", "923009998877", "what does it cost?"))
        db_session.refresh(wa_lead_no_optin)
        assert wa_lead_no_optin.whatsapp_last_inbound_at is not None
        row = optin_svc.latest_row(db_session, wa_lead_no_optin.id)
        assert row.status is m.OptInStatus.OPTED_IN
        assert row.source is m.OptInSource.INBOUND_MESSAGE
        reply = db_session.execute(select(m.InboundReply)).scalars().one()
        assert (reply.channel, reply.classification) == ("whatsapp", "question")

    def test_template_status_webhook_updates_our_row(self, client, db_session,
                                                     fake_claude,
                                                     approved_template):
        delivery = {"entry": [{"changes": [{
            "field": "message_template_status_update",
            "value": {"event": "REJECTED",
                      "message_template_id": approved_template.meta_template_id,
                      "message_template_name": approved_template.name,
                      "message_template_language": approved_template.language,
                      "reason": "SCAM"}}]}]}
        assert wa_signed_post(client, delivery).json()["processed"] == 1
        db_session.refresh(approved_template)
        assert approved_template.status is m.WhatsAppTemplateStatus.REJECTED
        assert approved_template.rejection_reason == "SCAM"


class TestOutcomeChannelCompleteness:
    def test_full_flow_every_outcome_row_has_correct_channel(
            self, client, db_session, fake_claude, multichannel_sequence,
            wa_lead, approved_template, gmail_account, fake_channel):
        """send email -> send WhatsApp -> read receipt -> WhatsApp reply ->
        STOP: every outcome row must carry its channel (M8 depends on it)."""
        from app.services.sequence_engine import enroll_leads
        from app.workers.outreach_tasks import send_message_impl
        from sqlalchemy import select as sel

        enroll_leads(db_session, multichannel_sequence, now=NOW)
        step1 = db_session.execute(sel(m.Message).where(
            m.Message.lead_id == wa_lead.id, m.Message.step_no == 1)
        ).scalars().one()
        assert send_message_impl(db_session, step1.id, channel=fake_channel,
                                 now=NOW) == "sent"
        step2 = db_session.execute(sel(m.Message).where(
            m.Message.lead_id == wa_lead.id, m.Message.step_no == 2)
        ).scalars().one()
        step2.scheduled_at = NOW
        db_session.commit()
        assert send_message_impl(db_session, step2.id, channel=fake_channel,
                                 now=NOW) == "sent"
        step2.provider_message_id = "wamid.FLOW1"
        db_session.commit()

        wa_signed_post(client, _status_delivery("wamid.FLOW1", "read"))
        fake_claude.default_reply_class = "interested"
        wa_signed_post(client, _inbound_delivery(
            "wamid.FLOW2", "923001234567", "very interested"))
        wa_signed_post(client, _inbound_delivery(
            "wamid.FLOW3", "923001234567", "STOP"))

        rows = db_session.execute(sel(m.Outcome).where(
            m.Outcome.lead_id == wa_lead.id)).scalars().all()
        by_event = {}
        for r in rows:
            by_event.setdefault(r.event, set()).add(r.channel)
        assert by_event[m.OutcomeEvent.SENT] == {"email", "whatsapp"}
        assert by_event[m.OutcomeEvent.OPENED] == {"whatsapp"}
        assert by_event[m.OutcomeEvent.REPLIED] == {"whatsapp"}
        assert by_event[m.OutcomeEvent.UNSUBSCRIBED] == {"whatsapp"}
        # nothing slipped through without a channel
        assert all(r.channel for r in rows)
