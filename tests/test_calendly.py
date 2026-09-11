"""Calendly webhooks, campaign overview, and sequence API endpoints."""

import hashlib
import hmac
import json

from sqlalchemy import select

from app.config import settings
from app.db import models as m
from app.workers.outreach_tasks import send_message_impl
from tests.conftest import NOW

SIGNING_KEY = "test-signing-key"


def signed_post(client, payload: dict, key: str = SIGNING_KEY):
    body = json.dumps(payload)
    ts = "1723300000"
    sig = hmac.new(key.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/calendly",
        content=body,
        headers={"Calendly-Webhook-Signature": f"t={ts},v1={sig}",
                 "Content-Type": "application/json"},
    )


def booking_payload(email: str, event: str = "invitee.created",
                    uri: str = "https://api.calendly.com/scheduled_events/EV1/invitees/INV1",
                    tenant_id=None):
    """An invitee webhook.

    `tenant_id` goes into payload.tracking, which is where Calendly returns the
    UTM parameter the booking link carries. webhooks.py resolves the account
    from it and quarantines a booking that has none, so a test asserting a
    match has to supply it. Leave it None to exercise the quarantine path.
    """
    from app.integrations.calendly import TENANT_TRACKING_PARAM

    payload = {"event": event, "payload": {"email": email, "uri": uri}}
    if tenant_id is not None:
        payload["payload"]["tracking"] = {TENANT_TRACKING_PARAM: str(tenant_id)}
    return payload


def _owner_of(db_session, lead):
    """The user id that owns a lead, via its strategy's product."""
    from app.services.notifications import owner_of_lead

    return owner_of_lead(db_session, lead)


class TestCalendlyWebhook:
    def _with_key(self, monkeypatch):
        monkeypatch.setattr(settings, "calendly_webhook_signing_key", SIGNING_KEY)

    def test_invalid_signature_rejected(self, leads_client, monkeypatch):
        self._with_key(monkeypatch)
        r = signed_post(leads_client, booking_payload("x@y.com"), key="wrong-key")
        assert r.status_code == 401

    def test_missing_signature_rejected(self, leads_client, monkeypatch):
        self._with_key(monkeypatch)
        r = leads_client.post("/webhooks/calendly", json=booking_payload("x@y.com"))
        assert r.status_code == 401

    def test_booking_updates_lead_and_stops_sequence(self, leads_client, db_session,
                                                     enrolled, verified_leads,
                                                     fake_channel, monkeypatch,
                                                     gmail_account):
        self._with_key(monkeypatch)
        lead = verified_leads[0]
        msg = db_session.execute(select(m.Message).where(
            m.Message.lead_id == lead.id)).scalar_one()
        send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)

        r = signed_post(leads_client, booking_payload(lead.email,
                                                      tenant_id=_owner_of(db_session, lead)))
        assert r.status_code == 200 and r.json()["action"] == "booked"
        assert lead.status is m.LeadStatus.MEETING_BOOKED
        e = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == lead.id)).scalar_one()
        assert e.status is m.EnrollmentStatus.STOPPED
        assert e.stop_reason == "meeting_booked"
        events = [o.event for o in db_session.execute(
            select(m.Outcome).where(m.Outcome.lead_id == lead.id)).scalars()]
        assert m.OutcomeEvent.BOOKED in events

    def test_duplicate_delivery_processed_once(self, leads_client, db_session,
                                               enrolled, verified_leads, monkeypatch):
        self._with_key(monkeypatch)
        lead = verified_leads[1]
        tenant = _owner_of(db_session, lead)
        first = signed_post(leads_client, booking_payload(lead.email, tenant_id=tenant))
        second = signed_post(leads_client, booking_payload(lead.email, tenant_id=tenant))
        assert first.json().get("action") == "booked"
        assert second.json() == {"ok": True, "duplicate": True}
        booked = [o for o in db_session.execute(
            select(m.Outcome).where(m.Outcome.lead_id == lead.id)).scalars()
            if o.event is m.OutcomeEvent.BOOKED]
        assert len(booked) == 1, "Calendly retries must not double-count"

    def test_cancellation_returns_lead_to_replied(self, leads_client, db_session,
                                                  enrolled, verified_leads, monkeypatch):
        self._with_key(monkeypatch)
        lead = verified_leads[2]
        tenant = _owner_of(db_session, lead)
        signed_post(leads_client, booking_payload(lead.email, tenant_id=tenant))
        r = signed_post(leads_client, booking_payload(
            lead.email, event="invitee.canceled",
            uri="https://api.calendly.com/scheduled_events/EV1/invitees/INV2",
            tenant_id=tenant))
        assert r.json()["action"] == "canceled"
        assert lead.status is m.LeadStatus.REPLIED


class TestSequenceApi:
    def test_create_sequence_with_steps(self, leads_client, verified_strategy):
        r = leads_client.post(f"/strategies/{verified_strategy.id}/sequences", json={
            "name": "Intro", "channel": "email",
            "booking_url": "https://calendly.com/founder/intro",
            "steps": [
                {"step_no": 1, "template": "intro", "delay_days": 0},
                {"step_no": 2, "template": "follow-up", "delay_days": 3},
            ],
        })
        assert r.status_code == 201, r.text
        assert [s["step_no"] for s in r.json()["steps"]] == [1, 2]

    def test_whatsapp_sequence_requires_template_linkedin_now_available(
            self, leads_client, verified_strategy):
        """MODIFIED in M4 Chunk 4 (was test_non_email_channel_rejected_in_m3)
        and again in Feature Group 5. A cold WhatsApp step without an
        approved-template reference is still rejected (422, template
        required). LinkedIn USED to be rejected as "not available yet"; it is
        a real channel since Feature Group 5, so a LinkedIn sequence is now
        created, with its steps defaulting to linkedin_action "auto"."""
        r = leads_client.post(f"/strategies/{verified_strategy.id}/sequences", json={
            "name": "WA", "channel": "whatsapp",
            "steps": [{"step_no": 1, "template": "hi"}],
        })
        assert r.status_code == 422
        assert "whatsapp_template_id" in r.json()["detail"]
        r = leads_client.post(f"/strategies/{verified_strategy.id}/sequences", json={
            "name": "LI", "channel": "linkedin",
            "steps": [{"step_no": 1, "template": "hi"}],
        })
        assert r.status_code == 201, r.text
        assert r.json()["steps"][0]["linkedin_action"] == "auto"

    def test_gapped_steps_rejected(self, leads_client, verified_strategy):
        r = leads_client.post(f"/strategies/{verified_strategy.id}/sequences", json={
            "name": "Bad", "channel": "email",
            "steps": [{"step_no": 1, "template": "a"}, {"step_no": 3, "template": "b"}],
        })
        assert r.status_code == 422

    def test_enroll_requires_verified_strategy(self, leads_client, db_session,
                                               product_with_strategy):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)  # pending
        seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL, name="s")
        db_session.add(seq)
        db_session.flush()
        db_session.add(m.SequenceStep(sequence_id=seq.id, step_no=1, template="t"))
        db_session.commit()
        r = leads_client.post(f"/sequences/{seq.id}/enroll", json={})
        assert r.status_code == 409

    def test_enroll_happy_path(self, leads_client, db_session, email_sequence,
                               verified_leads, gmail_account, fake_claude):
        r = leads_client.post(f"/sequences/{email_sequence.id}/enroll", json={})
        assert r.status_code == 202 and r.json() == {"enrolled": 3}
        detail = leads_client.get(f"/sequences/{email_sequence.id}").json()
        assert detail["enrollments"]["active"] == 3


class TestCampaignOverview:
    def test_overview_shape_and_rates(self, leads_client, db_session, enrolled,
                                      verified_leads, verified_strategy,
                                      fake_channel, gmail_account, fake_claude):
        lead = verified_leads[0]
        msg = db_session.execute(select(m.Message).where(
            m.Message.lead_id == lead.id)).scalar_one()
        send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)

        body = leads_client.get(f"/strategies/{verified_strategy.id}/campaign").json()
        assert body["campaign_state"] == "active"
        assert body["sent_total"] == 1
        assert body["leads_by_status"]["contacted"] == 1
        assert body["daily_cap_today"] == settings.gmail_daily_cap
        assert body["reply_rate"] == 0.0 and body["bounce_rate"] == 0.0
        assert body["meetings_booked"] == 0
        assert body["bounce_pause_threshold"] == settings.bounce_rate_pause_threshold
