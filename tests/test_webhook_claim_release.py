"""NEW-03 — a webhook event that FAILS must be processed when it is retried.

Both webhooks record the event id (processed_webhooks) and COMMIT it before
doing the work, so a retried delivery is recognised and skipped. But the
claim stayed in place when the work then raised: the provider got a 500 and
retried, the retry was answered "duplicate", and the event was never
processed. For a WhatsApp STOP that is an opt-out silently lost for good.

Now a handler that raises RELEASES its claim before the error propagates, so
the provider's retry is processed. A delivery that succeeded keeps its claim
and is still deduplicated. Retrying does not double-write the reply row or
the booking outcome.

The session here is configured like production (autoflush=False), and the
client reports an unhandled error as the HTTP 500 the provider would see.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db import models as m
from app.db.base import Base, get_db
from app.integrations import calendly
from app.integrations.calendly import TENANT_TRACKING_PARAM
from app.workers.lead_tasks import is_suppressed
from tests.conftest import NOW, wa_signed_post

WA_FROM = "923001234567"            # wa_lead's number as Meta sends it
CALENDLY_KEY = "claim-release-signing-key"
CALENDLY_NOW = 1_790_000_000


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def http(db_session, fake_claude):
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def fail_once(monkeypatch, target: str):
    """Make `target` raise the first time it is called, then behave normally.
    Returns a dict whose 'calls' counts every call."""
    module_path, name = target.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    real = getattr(module, name)
    state = {"calls": 0}

    def wrapper(*args, **kwargs):
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError(f"simulated failure in {name}")
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return state


def _claims(db_session, provider: str) -> list:
    return [row.event_id for row in db_session.execute(
        select(m.ProcessedWebhook).where(m.ProcessedWebhook.provider == provider)
    ).scalars().all()]


# --------------------------------------------------------------------------
# WhatsApp
# --------------------------------------------------------------------------


def _wa_messages(*messages) -> dict:
    return {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "5550001"},
        "messages": [{"id": wamid, "from": WA_FROM, "timestamp": "1754900000",
                      "type": "text", "text": {"body": text}}
                     for wamid, text in messages],
    }}]}]}


def _wa_status(wamid: str, status: str) -> dict:
    return {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "5550001"},
        "statuses": [{"id": wamid, "status": status, "timestamp": "1754900000",
                      "errors": [{"title": "Unreachable"}]}],
    }}]}]}


class TestWhatsAppStopSurvivesAFailure:
    def test_a_stop_that_failed_is_processed_when_meta_retries(
            self, http, db_session, wa_lead, monkeypatch):
        calls = fail_once(monkeypatch, "app.services.whatsapp_optin.revoke_opt_in")
        delivery = _wa_messages(("wamid.STOP-A", "STOP"))

        first = wa_signed_post(http, delivery)
        assert first.status_code == 500, "the simulated failure must surface as a 500"
        assert is_suppressed(db_session, phone=wa_lead.phone) is False

        retry = wa_signed_post(http, delivery)
        assert retry.status_code == 200, retry.text
        assert retry.json() == {"ok": True, "processed": 1, "duplicates": 0}
        assert calls["calls"] == 2
        assert is_suppressed(db_session, phone=wa_lead.phone) is True
        assert is_suppressed(db_session, email=wa_lead.email) is True
        db_session.refresh(wa_lead)
        assert wa_lead.whatsapp_opted_in is False

    def test_the_failed_event_leaves_no_claim_behind(
            self, http, db_session, wa_lead, monkeypatch):
        fail_once(monkeypatch, "app.services.whatsapp_optin.revoke_opt_in")
        assert wa_signed_post(http, _wa_messages(("wamid.STOP-B", "STOP"))).status_code == 500
        assert "wamid.STOP-B" not in _claims(db_session, "whatsapp")

    def test_the_retry_does_not_store_the_message_twice(
            self, http, db_session, wa_lead, monkeypatch):
        fail_once(monkeypatch, "app.services.whatsapp_optin.revoke_opt_in")
        delivery = _wa_messages(("wamid.STOP-C", "STOP"))
        wa_signed_post(http, delivery)
        assert wa_signed_post(http, delivery).status_code == 200

        replies = db_session.execute(select(m.InboundReply)).scalars().all()
        assert len(replies) == 1
        assert replies[0].classification == "unsubscribe_request"

    def test_a_successful_stop_is_still_deduplicated(self, http, db_session, wa_lead):
        delivery = _wa_messages(("wamid.STOP-D", "STOP"))
        assert wa_signed_post(http, delivery).json()["processed"] == 1
        again = wa_signed_post(http, delivery)
        assert again.json() == {"ok": True, "processed": 0, "duplicates": 1}
        assert _claims(db_session, "whatsapp").count("wamid.STOP-D") == 1

    def test_only_the_event_that_failed_is_reprocessed(
            self, http, db_session, wa_lead, monkeypatch):
        """One delivery, two messages: the first succeeds, the STOP fails.
        On the retry the first is a duplicate and the STOP is processed."""
        fail_once(monkeypatch, "app.services.whatsapp_optin.revoke_opt_in")
        delivery = _wa_messages(("wamid.HELLO-E", "what does it cost?"),
                                ("wamid.STOP-E", "STOP"))

        assert wa_signed_post(http, delivery).status_code == 500
        retry = wa_signed_post(http, delivery)
        assert retry.status_code == 200, retry.text
        assert retry.json() == {"ok": True, "processed": 1, "duplicates": 1}
        assert is_suppressed(db_session, phone=wa_lead.phone) is True


class TestWhatsAppStatusSurvivesAFailure:
    def test_a_failed_delivery_status_is_processed_on_retry(
            self, http, db_session, wa_lead, approved_template, monkeypatch):
        seq = m.Sequence(strategy_id=wa_lead.strategy_id, channel=m.ChannelType.WHATSAPP,
                         name="wa", status=m.SequenceStatus.ACTIVE)
        db_session.add(seq)
        db_session.flush()
        message = m.Message(sequence_id=seq.id, lead_id=wa_lead.id,
                            channel=m.ChannelType.WHATSAPP, step_no=1, template="t",
                            provider_message_id="wamid.SENT-F",
                            status=m.MessageStatus.SENT, sent_at=NOW)
        db_session.add(message)
        db_session.commit()
        fail_once(monkeypatch, "app.services.sequence_engine.record_bounce")
        delivery = _wa_status("wamid.SENT-F", "failed")

        assert wa_signed_post(http, delivery).status_code == 500
        retry = wa_signed_post(http, delivery)
        assert retry.status_code == 200, retry.text
        assert retry.json()["processed"] == 1
        db_session.refresh(wa_lead)
        assert wa_lead.status is m.LeadStatus.DROPPED       # the bounce path ran


# --------------------------------------------------------------------------
# Calendly
# --------------------------------------------------------------------------


@pytest.fixture()
def calendly_env(monkeypatch):
    monkeypatch.setattr(settings, "calendly_webhook_signing_key", CALENDLY_KEY)
    monkeypatch.setattr(calendly, "_now", lambda: float(CALENDLY_NOW))


def _calendly_post(client, payload: dict):
    body = json.dumps(payload)
    sig = hmac.new(CALENDLY_KEY.encode(), f"{CALENDLY_NOW}.{body}".encode(),
                   hashlib.sha256).hexdigest()
    return client.post("/webhooks/calendly", content=body,
                       headers={"Calendly-Webhook-Signature": f"t={CALENDLY_NOW},v1={sig}",
                                "Content-Type": "application/json"})


def _booking(lead, tenant_id, uri="https://api.calendly.com/scheduled_events/EV1/invitees/INV1"):
    return {"event": "invitee.created",
            "payload": {"email": lead.email, "uri": uri,
                        "tracking": {TENANT_TRACKING_PARAM: str(tenant_id)}}}


def _booked_outcomes(db_session, lead) -> list:
    return db_session.execute(select(m.Outcome).where(
        m.Outcome.lead_id == lead.id,
        m.Outcome.event == m.OutcomeEvent.BOOKED)).scalars().all()


class TestCalendlyBookingSurvivesAFailure:
    def test_a_booking_that_failed_is_processed_when_calendly_retries(
            self, http, db_session, verified_leads, test_user, calendly_env, monkeypatch):
        lead = verified_leads[0]
        calls = fail_once(monkeypatch, "app.workers.meeting_prep_tasks.request_prep")
        payload = _booking(lead, test_user.id)

        first = _calendly_post(http, payload)
        assert first.status_code == 500, "the simulated failure must surface as a 500"

        retry = _calendly_post(http, payload)
        assert retry.status_code == 200, retry.text
        assert retry.json() == {"ok": True, "matched": True, "action": "booked"}
        assert calls["calls"] == 2
        db_session.refresh(lead)
        assert lead.status is m.LeadStatus.MEETING_BOOKED

    def test_the_retry_does_not_count_the_booking_twice(
            self, http, db_session, verified_leads, test_user, calendly_env, monkeypatch):
        lead = verified_leads[0]
        fail_once(monkeypatch, "app.workers.meeting_prep_tasks.request_prep")
        payload = _booking(lead, test_user.id)
        _calendly_post(http, payload)
        assert _calendly_post(http, payload).status_code == 200

        assert len(_booked_outcomes(db_session, lead)) == 1
        assert len(_claims(db_session, "calendly")) == 1

    def test_a_successful_booking_is_still_deduplicated(
            self, http, db_session, verified_leads, test_user, calendly_env):
        lead = verified_leads[0]
        payload = _booking(lead, test_user.id)
        assert _calendly_post(http, payload).json()["action"] == "booked"
        assert _calendly_post(http, payload).json() == {"ok": True, "duplicate": True}
        assert len(_booked_outcomes(db_session, lead)) == 1
