"""F-SEC-02 — an inbound WhatsApp message must reach the right tenant's lead.

_handle_inbound scanned EVERY lead with a phone and took the first whose
normalised number matched. Two tenants can hold the same number, so a reply
(or a STOP) could be attached to a tenant that never messaged that person.

Rule (founder decision), among leads whose normalised phone equals the
sender's:
  (a) if any has been SENT a WhatsApp message, the lead of the MOST RECENT
      outbound WhatsApp message wins;
  (b) else, if EXACTLY ONE lead on the deployment holds the number, it is
      attached -- a prospect who messages us first still opens the 24h window
      and records the initiation opt-in;
  (c) else (several leads, none messaged) it is ambiguous: attached to none,
      200, nothing written.
A STOP that reaches no lead still adds one global phone suppression row,
because an opt-out must never be dropped.

The STOP tests run on a session configured like production (autoflush=False),
for the reason given in tests/test_whatsapp_stop_suppression.py.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models as m
from app.db.base import Base, get_db
from app.workers.lead_tasks import is_suppressed
from tests.conftest import wa_signed_post

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
DIGITS = "923001112233"          # how Meta sends the number
E164 = "+923001112233"           # how an opted-in lead's phone is stored


def _inbound(wamid: str, text: str, from_phone: str = DIGITS) -> dict:
    return {"entry": [{"changes": [{"field": "messages", "value": {
        "metadata": {"phone_number_id": "5550001"},
        "messages": [{"id": wamid, "from": from_phone,
                      "timestamp": "1754900000", "type": "text",
                      "text": {"body": text}}],
    }}]}]}


def _tenant(db_session, tag: str) -> m.Strategy:
    user = m.User(email=f"tenant-{tag.lower()}-fsec02@test.dev", email_verified=True)
    db_session.add(user)
    db_session.flush()
    product = m.Product(user=user, name=f"Product {tag}",
                        description=f"Product of tenant {tag}",
                        type=m.ProductType.SKILL)
    db_session.add(product)
    db_session.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
    db_session.add(strategy)
    db_session.commit()
    return strategy


def _lead(db_session, strategy: m.Strategy, tag: str, phone: str = E164) -> m.Lead:
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=f"FSEC02-{tag}",
                  full_name=f"Lead {tag}", company=f"Company {tag}",
                  email=f"lead-{tag.lower()}@fsec02.test", phone=phone,
                  status=m.LeadStatus.CONTACTED)
    db_session.add(lead)
    db_session.commit()
    return lead


def _whatsapp_sent(db_session, lead: m.Lead, when: datetime) -> m.Message:
    """One outbound WhatsApp message to this lead, already sent."""
    seq = m.Sequence(strategy_id=lead.strategy_id, channel=m.ChannelType.WHATSAPP,
                     name=f"wa-{lead.external_id}", status=m.SequenceStatus.ACTIVE)
    db_session.add(seq)
    db_session.flush()
    message = m.Message(sequence_id=seq.id, lead_id=lead.id,
                        channel=m.ChannelType.WHATSAPP, step_no=1, template="t",
                        body="hello", status=m.MessageStatus.SENT, sent_at=when)
    db_session.add(message)
    db_session.commit()
    return message


def _replies(db_session) -> list:
    return db_session.execute(select(m.InboundReply)).scalars().all()


def _untouched(db_session, lead: m.Lead) -> bool:
    db_session.refresh(lead)
    return (lead.whatsapp_last_inbound_at is None
            and lead.status is m.LeadStatus.CONTACTED
            and lead.whatsapp_opted_in is False)


# --------------------------------------------------------------------------
# Which tenant's lead gets the reply
# --------------------------------------------------------------------------


class TestTenantResolvedFromOutboundHistory:
    def test_the_reply_goes_to_the_tenant_that_messaged_the_number(
            self, client, db_session, fake_claude):
        """A is created first, so the old first-match scan picked A."""
        lead_a = _lead(db_session, _tenant(db_session, "A"), "A")
        lead_b = _lead(db_session, _tenant(db_session, "B"), "B")
        _whatsapp_sent(db_session, lead_b, NOW - timedelta(hours=2))

        assert wa_signed_post(client, _inbound("wamid.M1", "sounds good")).status_code == 200

        replies = _replies(db_session)
        assert [r.lead_id for r in replies] == [lead_b.id]
        db_session.refresh(lead_b)
        assert lead_b.whatsapp_last_inbound_at is not None
        assert _untouched(db_session, lead_a)

    def test_when_both_messaged_it_the_most_recent_outbound_wins(
            self, client, db_session, fake_claude):
        lead_a = _lead(db_session, _tenant(db_session, "A"), "A")
        lead_b = _lead(db_session, _tenant(db_session, "B"), "B")
        _whatsapp_sent(db_session, lead_a, NOW - timedelta(days=3))
        _whatsapp_sent(db_session, lead_b, NOW - timedelta(hours=1))

        assert wa_signed_post(client, _inbound("wamid.M2", "sounds good")).status_code == 200

        assert [r.lead_id for r in _replies(db_session)] == [lead_b.id]
        assert _untouched(db_session, lead_a)

    def test_most_recent_is_decided_by_send_time_not_by_creation_order(
            self, client, db_session, fake_claude):
        lead_a = _lead(db_session, _tenant(db_session, "A"), "A")
        lead_b = _lead(db_session, _tenant(db_session, "B"), "B")
        _whatsapp_sent(db_session, lead_b, NOW - timedelta(days=3))
        _whatsapp_sent(db_session, lead_a, NOW - timedelta(hours=1))

        assert wa_signed_post(client, _inbound("wamid.M3", "sounds good")).status_code == 200

        assert [r.lead_id for r in _replies(db_session)] == [lead_a.id]
        assert _untouched(db_session, lead_b)

    def test_stored_phone_formatting_does_not_prevent_the_match(
            self, client, db_session, fake_claude):
        lead = _lead(db_session, _tenant(db_session, "A"), "A",
                     phone="+92 300-111 2233")
        _whatsapp_sent(db_session, lead, NOW - timedelta(hours=1))

        assert wa_signed_post(client, _inbound("wamid.M4", "sounds good")).status_code == 200

        assert [r.lead_id for r in _replies(db_session)] == [lead.id]

    def test_an_email_to_the_lead_is_not_whatsapp_history(
            self, client, db_session, fake_claude):
        """A emailed the person an hour ago; B WhatsApp-messaged them last
        week. Only WhatsApp history resolves a WhatsApp reply."""
        lead_a = _lead(db_session, _tenant(db_session, "A"), "A")
        lead_b = _lead(db_session, _tenant(db_session, "B"), "B")
        seq = m.Sequence(strategy_id=lead_a.strategy_id, channel=m.ChannelType.EMAIL,
                         name="email", status=m.SequenceStatus.ACTIVE)
        db_session.add(seq)
        db_session.flush()
        db_session.add(m.Message(sequence_id=seq.id, lead_id=lead_a.id,
                                 channel=m.ChannelType.EMAIL, step_no=1, template="t",
                                 status=m.MessageStatus.SENT,
                                 sent_at=NOW - timedelta(hours=1)))
        db_session.commit()
        _whatsapp_sent(db_session, lead_b, NOW - timedelta(days=7))

        assert wa_signed_post(client, _inbound("wamid.M5", "sounds good")).status_code == 200

        assert [r.lead_id for r in _replies(db_session)] == [lead_b.id]
        assert _untouched(db_session, lead_a)


class TestNoOutboundHistory:
    def test_the_only_lead_with_the_number_is_attached(
            self, client, db_session, fake_claude):
        """Rule (b): the prospect messaged us first. Exactly one lead holds
        the number, so there is nothing to disambiguate -- the 24h window
        opens and the initiation opt-in is recorded, as before."""
        from app.services import whatsapp_optin as optin_svc

        lead = _lead(db_session, _tenant(db_session, "A"), "A")

        response = wa_signed_post(client, _inbound("wamid.N1", "do you do audits?"))
        assert response.status_code == 200, response.text

        assert [r.lead_id for r in _replies(db_session)] == [lead.id]
        db_session.refresh(lead)
        assert lead.whatsapp_last_inbound_at is not None
        row = optin_svc.latest_row(db_session, lead.id)
        assert row.status is m.OptInStatus.OPTED_IN
        assert row.source is m.OptInSource.INBOUND_MESSAGE

    def test_several_leads_and_no_history_is_ambiguous_and_attaches_to_none(
            self, client, db_session, fake_claude):
        """Rule (c): two tenants hold the number, neither messaged it. There
        is no basis for choosing, so neither gets the message."""
        lead_a = _lead(db_session, _tenant(db_session, "A"), "A")
        lead_b = _lead(db_session, _tenant(db_session, "B"), "B")

        response = wa_signed_post(client, _inbound("wamid.N2", "who is this?"))
        assert response.status_code == 200, response.text

        assert _replies(db_session) == []
        assert _untouched(db_session, lead_a)
        assert _untouched(db_session, lead_b)
        assert db_session.execute(select(m.WhatsAppOptIn)).scalars().all() == []
        assert db_session.execute(select(m.SuppressionEntry)).scalars().all() == []

    def test_a_number_no_lead_holds_writes_nothing(
            self, client, db_session, fake_claude):
        response = wa_signed_post(client, _inbound("wamid.N3", "hello?"))
        assert response.status_code == 200, response.text

        assert _replies(db_session) == []
        assert db_session.execute(select(m.SuppressionEntry)).scalars().all() == []


# --------------------------------------------------------------------------
# STOP — on a production-like session (autoflush=False)
# --------------------------------------------------------------------------


@pytest.fixture()
def prod_session():
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
def prod_http(prod_session):
    from app.main import app

    app.dependency_overrides[get_db] = lambda: prod_session
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        app.dependency_overrides.clear()


def _suppressed_phones(session) -> list:
    return [row.phone for row in
            session.execute(select(m.SuppressionEntry)).scalars().all()]


class TestStopFromAnUnmatchedNumber:
    def test_it_adds_exactly_one_global_phone_suppression_row(
            self, prod_http, prod_session):
        assert prod_session.autoflush is False
        response = wa_signed_post(prod_http, _inbound("wamid.S1", "STOP"))
        assert response.status_code == 200, response.text

        assert _suppressed_phones(prod_session) == [E164]
        # The format the send-time check compares for a WhatsApp recipient.
        assert is_suppressed(prod_session, phone=E164) is True
        assert _replies(prod_session) == []

    def test_it_is_idempotent_for_a_redelivery_and_for_a_second_stop(
            self, prod_http, prod_session):
        assert wa_signed_post(prod_http, _inbound("wamid.S2", "STOP")).status_code == 200
        assert wa_signed_post(prod_http, _inbound("wamid.S2", "STOP")).status_code == 200
        assert wa_signed_post(prod_http, _inbound("wamid.S3", "stop")).status_code == 200

        assert _suppressed_phones(prod_session) == [E164]

    def test_an_ambiguous_stop_suppresses_the_phone_and_modifies_no_lead(
            self, prod_http, prod_session):
        """Rule (c) + STOP: two tenants hold the number, neither messaged it.
        Neither lead is touched, but the number is suppressed for everyone."""
        lead_a = _lead(prod_session, _tenant(prod_session, "A"), "A")
        lead_b = _lead(prod_session, _tenant(prod_session, "B"), "B")

        assert wa_signed_post(prod_http, _inbound("wamid.S4", "STOP")).status_code == 200
        assert wa_signed_post(prod_http, _inbound("wamid.S4b", "STOP")).status_code == 200

        assert _suppressed_phones(prod_session) == [E164]
        assert _untouched(prod_session, lead_a)
        assert _untouched(prod_session, lead_b)
        assert prod_session.execute(select(m.WhatsAppOptIn)).scalars().all() == []
        assert _replies(prod_session) == []
        assert is_suppressed(prod_session, phone=lead_a.phone) is True
        assert is_suppressed(prod_session, phone=lead_b.phone) is True

    def test_a_stop_from_the_only_lead_with_the_number_is_a_full_opt_out(
            self, prod_http, prod_session):
        """Rule (b) + STOP: one lead, never messaged. The STOP is theirs, so
        it gets the audit row and the email suppression, not just the phone."""
        lead = _lead(prod_session, _tenant(prod_session, "A"), "A")

        response = wa_signed_post(prod_http, _inbound("wamid.S4c", "STOP"))
        assert response.status_code == 200, response.text

        optouts = prod_session.execute(select(m.WhatsAppOptIn)).scalars().all()
        assert [(row.lead_id, row.status) for row in optouts] == [
            (lead.id, m.OptInStatus.OPTED_OUT)]
        assert _suppressed_phones(prod_session).count(E164) == 1
        assert is_suppressed(prod_session, email=lead.email) is True

    def test_a_non_stop_message_from_an_unmatched_number_suppresses_nothing(
            self, prod_http, prod_session):
        assert wa_signed_post(prod_http, _inbound("wamid.S5", "hello?")).status_code == 200
        assert _suppressed_phones(prod_session) == []


class TestStopFromAMatchedNumber:
    def test_it_suppresses_only_the_tenant_that_messaged_and_everything_global(
            self, prod_http, prod_session):
        """The opt-in audit row and sequence stop land on B's lead; the
        suppression rows are global, so A cannot message the number either."""
        lead_a = _lead(prod_session, _tenant(prod_session, "A"), "A")
        lead_b = _lead(prod_session, _tenant(prod_session, "B"), "B")
        _whatsapp_sent(prod_session, lead_b, NOW - timedelta(hours=1))

        response = wa_signed_post(prod_http, _inbound("wamid.S6", "STOP"))
        assert response.status_code == 200, response.text

        optouts = prod_session.execute(select(m.WhatsAppOptIn)).scalars().all()
        assert [row.lead_id for row in optouts] == [lead_b.id]
        assert _suppressed_phones(prod_session).count(E164) == 1
        assert is_suppressed(prod_session, phone=lead_a.phone) is True
        assert is_suppressed(prod_session, email=lead_b.email) is True
        assert is_suppressed(prod_session, email=lead_a.email) is False
