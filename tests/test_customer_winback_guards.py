"""LEGAL / SAFETY GUARD tests for customer win-back (local business mode).

Kept in one file so they can be sealed (evals/compliance_testset.yaml):
  * the send-time guard `local_business.customer_send_block`: audience
    mismatch, flag off, channel, healthcare, missing / withdrawn consent,
    automatic re-engagement touches; lookup error fails closed;
  * H1 -- a person who opted out (suppression list, or a withdrawn /
    suppressed / erased event in the consent ledger, on ANY identifier in
    the row) is never re-imported, whatever consent_date the CSV claims, and
    an import never creates a second record for the same person;
  * H2 -- AI voice calls, phone consent and API WhatsApp opt-ins are refused
    for imported customers through one shared guard
    (`local_business.channel_refusal` / `local_business.is_customer`);
  * Reply Copilot never auto-answers a customer.

Spec: docs/features/local-business-mode.md. Offline: SQLite, FakeClaude,
FakeChannel, no network.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import consent
from app.services import local_business as lb
from app.services import sequence_engine as engine
from app.services import system_settings
from app.workers.outreach_tasks import send_message_impl
from tests.conftest import NOW, entitle_owner

HEADER = "name,email,phone,consent_channels,consent_date,consent_source,consent_text"
SARA = "Sara Khan,sara@example.com,,email,2026-03-01,loyalty sign-up form at the till,"
STEP_TEMPLATE = ("Subject: We miss you, {first_name}\n"
                 "Hi {first_name}, {business_name} has a new autumn menu this week. "
                 "Come and say hello.")


def _csv(*rows: str, header: str = HEADER) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode()


def _import(client, strategy, data: bytes):
    return client.post(f"/strategies/{strategy.id}/customers/import",
                       files={"file": ("customers.csv", data, "text/csv")},
                       data={"attestation": lb.ATTESTATION})


@pytest.fixture()
def local_strategy(db_session, verified_strategy):
    product = db_session.get(m.Product, verified_strategy.product_id)
    product.business_type = "restaurant"
    product.name = "Bella Cafe"
    db_session.commit()
    return verified_strategy


@pytest.fixture()
def winback_on(db_session):
    system_settings.set(db_session, lb.WINBACK_FLAG, True)


def _customers(db, strategy):
    return db.execute(select(m.Lead).where(m.Lead.strategy_id == strategy.id,
                                           m.Lead.source == lb.CUSTOMER_SOURCE)
                      ).scalars().all()


def _customer(db, strategy, email="sara@example.com", name="Sara Khan", consented=True,
              phone=None):
    lead = m.Lead(strategy_id=strategy.id, source=lb.CUSTOMER_SOURCE, full_name=name,
                  email=email, phone=phone, status=m.LeadStatus.SOURCED)
    db.add(lead)
    db.commit()
    if consented and email:
        consent.record(db, lead=lead, kind=consent.GRANTED, channel=consent.EMAIL,
                       source=lb.CUSTOMER_SOURCE, identifier=email,
                       detail="opted in to marketing on 2026-03-01 via web form")
    return lead


def _customer_sequence(db, strategy):
    seq = m.Sequence(strategy_id=strategy.id, channel=m.ChannelType.EMAIL, name="Win-back",
                     status=m.SequenceStatus.ACTIVE, audience=lb.AUDIENCE_CUSTOMERS)
    db.add(seq)
    db.flush()
    db.add(m.SequenceStep(sequence_id=seq.id, step_no=1, template=STEP_TEMPLATE,
                          delay_days=0, followup_enabled=False))
    db.commit()
    return seq


def _pending(db, lead):
    return db.execute(select(m.Message).where(
        m.Message.lead_id == lead.id,
        m.Message.status == m.MessageStatus.SCHEDULED)).scalars().first()


# --------------------------------------------------------------------------
# The send-time guard
# --------------------------------------------------------------------------


class TestSendPath:
    @pytest.fixture()
    def ready(self, db_session, local_strategy, gmail_account, winback_on):
        customer = _customer(db_session, local_strategy)
        seq = _customer_sequence(db_session, local_strategy)
        engine.enroll_leads(db_session, seq, now=NOW)
        return customer, seq

    def test_consented_customer_gets_the_owners_copy(self, db_session, ready, fake_channel,
                                                     fake_claude):
        customer, _ = ready
        msg = _pending(db_session, customer)
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"
        sent = fake_channel.sent[0]
        assert sent.subject == "We miss you, Sara"
        assert sent.body.startswith("Hi Sara, Bella Cafe has a new autumn menu this week.")
        assert "/unsubscribe/" in sent.body
        assert sent.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert "html_body" not in (sent.metadata or {}), "no tracking pixel for consumers"
        assert fake_claude.personalization_calls == [], "no model writes to a consumer"
        audit = db_session.execute(select(m.ComplianceAuditLog.decision).where(
            m.ComplianceAuditLog.lead_id == customer.id)).scalars().all()
        assert "sent" in audit

    def test_withdrawn_consent_is_never_sent(self, db_session, ready, fake_channel):
        customer, _ = ready
        consent.record(db_session, lead=customer, kind=consent.WITHDRAWN,
                       channel=consent.EMAIL, source="manual")
        msg = _pending(db_session, customer)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == lb.SEND_RESULT
        assert fake_channel.sent == []
        assert msg.status is m.MessageStatus.CANCELLED
        assert msg.error.startswith(lb.ERROR_PREFIX)
        enrollment = db_session.execute(select(m.SequenceEnrollment).where(
            m.SequenceEnrollment.lead_id == customer.id)).scalar_one()
        assert enrollment.status is m.EnrollmentStatus.STOPPED
        assert enrollment.stop_category == "suppressed"

    def test_unsubscribed_customer_is_never_sent(self, db_session, ready, fake_channel):
        customer, _ = ready
        consent.suppress_everywhere(db_session, customer, source="unsubscribe_link",
                                    reason="unsubscribed")
        msg = db_session.execute(select(m.Message).where(
            m.Message.lead_id == customer.id)).scalars().first()
        msg.status = m.MessageStatus.SCHEDULED
        db_session.commit()
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "cancelled_suppressed"
        assert fake_channel.sent == []

    def test_no_recorded_consent_is_never_sent(self, db_session, local_strategy,
                                               gmail_account, winback_on, fake_channel):
        customer = _customer(db_session, local_strategy, consented=False)
        engine.enroll_leads(db_session, _customer_sequence(db_session, local_strategy),
                            now=NOW)
        msg = _pending(db_session, customer)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == lb.SEND_RESULT
        assert fake_channel.sent == []

    def test_flag_switched_off_after_launch_is_never_sent(self, db_session, ready,
                                                          fake_channel):
        customer, _ = ready
        system_settings.set(db_session, lb.WINBACK_FLAG, False)
        msg = _pending(db_session, customer)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == lb.SEND_RESULT
        assert fake_channel.sent == []
        assert "switched off" in msg.error

    def test_product_turned_healthcare_is_never_sent(self, db_session, ready, local_strategy,
                                                     fake_channel):
        customer, _ = ready
        db_session.get(m.Product, local_strategy.product_id).business_type = "healthcare"
        db_session.commit()
        msg = _pending(db_session, customer)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == lb.SEND_RESULT
        assert "HIPAA" in msg.error and fake_channel.sent == []

    def test_prospect_in_a_customer_sequence_is_never_sent(self, db_session, local_strategy,
                                                           verified_leads, gmail_account,
                                                           fake_channel, winback_on):
        seq = _customer_sequence(db_session, local_strategy)
        prospect = verified_leads[0]
        enrollment = m.SequenceEnrollment(sequence_id=seq.id, lead_id=prospect.id)
        db_session.add(enrollment)
        db_session.flush()
        msg = m.Message(lead_id=prospect.id, sequence_id=seq.id, step_no=1,
                        channel=m.ChannelType.EMAIL, template=STEP_TEMPLATE,
                        status=m.MessageStatus.SCHEDULED, scheduled_at=NOW)
        db_session.add(msg)
        db_session.commit()
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == lb.SEND_RESULT
        assert fake_channel.sent == []

    def test_customer_in_a_prospect_sequence_is_never_sent(self, db_session, local_strategy,
                                                           email_sequence, gmail_account,
                                                           fake_channel, winback_on):
        customer = _customer(db_session, local_strategy)
        enrollment = m.SequenceEnrollment(sequence_id=email_sequence.id, lead_id=customer.id)
        db_session.add(enrollment)
        db_session.flush()
        msg = m.Message(lead_id=customer.id, sequence_id=email_sequence.id, step_no=1,
                        channel=m.ChannelType.EMAIL, template="Step 1 brief",
                        status=m.MessageStatus.SCHEDULED, scheduled_at=NOW)
        db_session.add(msg)
        db_session.commit()
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == lb.SEND_RESULT
        assert fake_channel.sent == []

    def test_automatic_reengagement_touch_is_never_sent(self, db_session, ready,
                                                        fake_channel):
        from app.services import reengagement_memory

        customer, _ = ready
        msg = _pending(db_session, customer)
        msg.origin = reengagement_memory.ORIGIN
        db_session.commit()
        assert lb.customer_send_block(db_session, customer, db_session.get(
            m.Sequence, msg.sequence_id), msg, db_session.get(
            m.Strategy, customer.strategy_id)) is not None

    def test_lookup_error_fails_closed(self, db_session, ready, fake_channel, monkeypatch):
        customer, _ = ready

        def boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(lb, "customer_send_block", boom)
        msg = _pending(db_session, customer)
        out = send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert out == "deferred_winback_unavailable"
        assert fake_channel.sent == []
        assert msg.status is m.MessageStatus.SCHEDULED

    def test_ordinary_b2b_sends_are_unaffected(self, db_session, enrolled, fake_channel):
        msg = db_session.execute(select(m.Message).where(
            m.Message.sequence_id == enrolled.id)).scalars().first()
        assert send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW) == "sent"




# --------------------------------------------------------------------------
# H1 -- an opt-out is final: no re-import, no second record
# --------------------------------------------------------------------------


class TestReimportAfterOptOut:
    WA_ROW = ("Sara Khan,sara@example.com,+12125550100,email;whatsapp,{date},web form,")

    def _first_then_unsubscribe(self, client, db_session, local_strategy):
        r = _import(client, local_strategy, _csv(SARA))
        first = db_session.get(m.Lead, uuid.UUID(r.json()["accepted"][0]["lead_id"]))
        consent.suppress_everywhere(db_session, first, source="unsubscribe_link",
                                    reason="unsubscribed")
        return first

    @pytest.mark.parametrize("consent_date", ["2026-03-01", "2026-09-30"])
    def test_whole_row_refused_whatever_consent_date(self, client, db_session,
                                                     local_strategy, winback_on,
                                                     consent_date):
        first = self._first_then_unsubscribe(client, db_session, local_strategy)
        r = _import(client, local_strategy, _csv(self.WA_ROW.format(date=consent_date)))
        assert r.status_code == 200, r.text
        assert r.json()["accepted"] == []
        assert "opted out" in r.json()["rejected"][0]["reason"]
        assert [c.id for c in _customers(db_session, local_strategy)] == [first.id]
        assert db_session.execute(select(m.WhatsAppOptIn)).scalars().all() == []
        db_session.refresh(first)
        assert first.phone is None and first.whatsapp_opted_in is False

    def test_reported_path_never_reaches_whatsapp(self, client, db_session, local_strategy,
                                                  winback_on, approved_template,
                                                  fake_channel):
        """The reviewer's P5c path end to end: opt out, re-import with a phone,
        launch a WhatsApp win-back -- nothing is sent to anyone."""
        entitle_owner(db_session, local_strategy, m.PlanTier.STARTER)
        self._first_then_unsubscribe(client, db_session, local_strategy)
        _import(client, local_strategy, _csv(self.WA_ROW.format(date="2026-03-01")))
        r = client.post(f"/strategies/{local_strategy.id}/sequences",
                        json={"name": "WA", "audience": "customers", "channel": "whatsapp",
                              "steps": [{"step_no": 1, "template": "wa", "delay_days": 0,
                                         "whatsapp_template_id": str(approved_template.id),
                                         "variable_mapping": {"1": "lead.first_name",
                                                              "2": "lead.full_name"}}]})
        assert r.status_code == 201, r.text
        seq = db_session.get(m.Sequence, uuid.UUID(r.json()["id"]))
        seq.status = m.SequenceStatus.ACTIVE
        db_session.commit()
        engine.enroll_leads(db_session, seq, now=NOW)
        for msg in db_session.execute(select(m.Message).where(
                m.Message.sequence_id == seq.id)).scalars().all():
            send_message_impl(db_session, msg.id, channel=fake_channel, now=NOW)
        assert fake_channel.sent == []

    @pytest.mark.parametrize("suppressed", [
        {"phone": "+12125550100"}, {"email": "sara@example.com"}])
    def test_any_suppressed_identifier_refuses_the_whole_row(self, client, db_session,
                                                             local_strategy, winback_on,
                                                             suppressed):
        db_session.add(m.SuppressionEntry(reason="unsubscribed", **suppressed))
        db_session.commit()
        r = _import(client, local_strategy, _csv(
            "Sara,sara@example.com,+12125550100,email;whatsapp,2026-03-01,web form,"))
        assert r.json()["accepted"] == []
        assert "opted out" in r.json()["rejected"][0]["reason"]
        assert _customers(db_session, local_strategy) == []
        assert db_session.execute(select(m.ConsentEvent)).scalars().all() == []

    def test_unconsented_identifier_on_the_row_still_counts(self, client, db_session,
                                                            local_strategy, winback_on):
        """WhatsApp-only consent, but the row's (unused) email opted out."""
        db_session.add(m.SuppressionEntry(email="sara@example.com", reason="unsubscribed"))
        db_session.commit()
        r = _import(client, local_strategy, _csv(
            "Sara,sara@example.com,+12125550100,whatsapp,2026-03-01,web form,"))
        assert r.json()["accepted"] == []
        assert _customers(db_session, local_strategy) == []

    def test_suppressed_linkedin_identifier_refuses_the_row(self, client, db_session,
                                                            local_strategy, winback_on):
        db_session.add(m.LinkedInSuppression(profile="sara-khan", reason="unsubscribed"))
        db_session.commit()
        r = _import(client, local_strategy, _csv(
            "Sara,sara@example.com,email,2026-03-01,web form,"
            "https://www.linkedin.com/in/sara-khan",
            header="name,email,consent_channels,consent_date,consent_source,linkedin"))
        assert r.json()["accepted"] == []
        assert "opted out" in r.json()["rejected"][0]["reason"]

    def test_ledger_withdrawal_without_suppression_still_refuses(self, client, db_session,
                                                                 local_strategy, winback_on,
                                                                 test_user):
        consent.record(db_session, lead=None, kind=consent.WITHDRAWN, channel=consent.ALL,
                       source="manual", identifier="sara@example.com",
                       user_id=test_user.id)
        r = _import(client, local_strategy, _csv(SARA))
        assert r.json()["accepted"] == []
        assert "opted out" in r.json()["rejected"][0]["reason"]

    def test_erased_person_is_never_reimported(self, client, db_session, local_strategy,
                                               winback_on, test_user):
        consent.record(db_session, lead=None, kind=consent.ERASED, channel=consent.ALL,
                       source="gdpr_request", identifier="+12125550100",
                       user_id=test_user.id)
        r = _import(client, local_strategy, _csv(
            "Sara,,+12125550100,whatsapp,2026-03-01,web form,"))
        assert r.json()["accepted"] == []

    def test_same_person_by_phone_is_never_a_second_record(self, client, db_session,
                                                           local_strategy, winback_on):
        r = _import(client, local_strategy, _csv(
            "Sara,,+12125550100,whatsapp,2026-03-01,web form,"))
        first = uuid.UUID(r.json()["accepted"][0]["lead_id"])
        r = _import(client, local_strategy, _csv(
            "Sara,sara@example.com,+12125550100,email;whatsapp,2026-04-01,web form,"))
        assert uuid.UUID(r.json()["accepted"][0]["lead_id"]) == first
        assert len(_customers(db_session, local_strategy)) == 1

    def test_send_guard_blocks_a_customer_with_a_later_ledger_opt_out(
            self, db_session, local_strategy, winback_on, approved_template, fake_channel):
        """Defence in depth: a WhatsApp opt-in row still says opted_in, but the
        ledger holds an 'all channels' withdrawal for the person."""
        from app.services import whatsapp_optin

        entitle_owner(db_session, local_strategy, m.PlanTier.STARTER)
        customer = _customer(db_session, local_strategy, email=None, phone="+12125550100")
        whatsapp_optin.record_opt_in(db_session, customer, source=m.OptInSource.MANUAL_IMPORT,
                                     evidence="opted in to marketing on 2026-03-01 via QR")
        consent.record(db_session, lead=customer, kind=consent.WITHDRAWN,
                       channel=consent.ALL, source="manual")
        seq = m.Sequence(strategy_id=local_strategy.id, channel=m.ChannelType.WHATSAPP,
                         name="WA", status=m.SequenceStatus.ACTIVE,
                         audience=lb.AUDIENCE_CUSTOMERS)
        db_session.add(seq)
        db_session.flush()
        db_session.add(m.SequenceStep(
            sequence_id=seq.id, step_no=1, template="wa",
            whatsapp_kind=m.WhatsAppStepKind.TEMPLATE,
            whatsapp_template_id=approved_template.id,
            variable_mapping_json={"1": "lead.first_name", "2": "lead.full_name"}))
        db_session.commit()
        engine.enroll_leads(db_session, seq, now=NOW)
        msg = _pending(db_session, customer)
        assert send_message_impl(db_session, msg.id, channel=fake_channel,
                                 now=NOW) == lb.SEND_RESULT
        assert fake_channel.sent == []


# --------------------------------------------------------------------------
# H2 -- one channel question for every entry point
# --------------------------------------------------------------------------


class TestChannelEntryPoints:
    @pytest.fixture()
    def phone_customer(self, db_session, local_strategy, winback_on):
        entitle_owner(db_session, local_strategy, m.PlanTier.SCALE)
        system_settings.set(db_session, "phone_calling_enabled", True)
        return _customer(db_session, local_strategy, email=None, phone="+12125550100")

    def test_shared_guard(self, db_session, local_strategy, verified_leads):
        customer = _customer(db_session, local_strategy)
        for channel in ("email", "whatsapp", m.ChannelType.EMAIL):
            assert lb.channel_refusal(customer, channel) is None
        for channel in ("phone", "linkedin", m.ChannelType.PHONE, "sms"):
            assert lb.channel_refusal(customer, channel)
        assert lb.channel_refusal(verified_leads[0], "phone") is None

    def test_phone_consent_is_refused(self, client, db_session, phone_customer):
        r = client.put(f"/leads/{phone_customer.id}/phone-consent", json={"source": "said yes"})
        assert r.status_code == 409 and "customer" in r.json()["detail"]
        db_session.refresh(phone_customer)
        assert phone_customer.phone_consent_at is None

    def test_ai_call_is_refused_before_any_provider(self, client, db_session, phone_customer,
                                                    monkeypatch):
        from app.services import phone_calls

        reserved: list = []
        monkeypatch.setattr(phone_calls, "reserve_call_slot",
                            lambda *a, **k: reserved.append(a) or True)
        phone_customer.phone_consent_at = NOW          # even if set by hand
        db_session.commit()
        r = client.post(f"/leads/{phone_customer.id}/call", json={"brief": "win-back"})
        assert r.status_code == 409 and "customer" in r.json()["detail"]
        assert reserved == []
        assert db_session.execute(select(m.Call)).scalars().all() == []

    def test_phone_consent_never_counts_for_a_customer(self, db_session, phone_customer):
        from app.services import phone_calls

        system_settings.set(db_session, "phone_require_consent", False)
        phone_customer.phone_consent_at = NOW
        db_session.commit()
        assert phone_calls.consent_ok(db_session, phone_customer) is False

    def test_api_whatsapp_optin_is_refused(self, client, db_session, phone_customer):
        r = client.post(f"/leads/{phone_customer.id}/whatsapp-optin",
                        json={"source": "api", "evidence": "said yes on the phone"})
        assert r.status_code == 409 and "customer" in r.json()["detail"]
        assert db_session.execute(select(m.WhatsAppOptIn)).scalars().all() == []

    def test_whatsapp_optin_csv_never_matches_a_customer(self, client, db_session,
                                                         phone_customer):
        data = b"phone,evidence,consent_text\n+12125550100,signed form,yes\n"
        r = client.post("/whatsapp/optins/import",
                        files={"file": ("o.csv", data, "text/csv")})
        assert r.status_code == 200
        assert r.json()["accepted"] == []
        assert db_session.execute(select(m.WhatsAppOptIn)).scalars().all() == []

# Reply Copilot


class TestReplyCopilot:
    def test_customer_is_never_auto_answered(self, db_session, local_strategy, monkeypatch):
        from app.services import reply_copilot

        customer = _customer(db_session, local_strategy)
        monkeypatch.setattr(reply_copilot, "auto_send_allowed", lambda db: True)
        monkeypatch.setattr(reply_copilot, "auto_send_opted_in", lambda db, uid: True)
        draft = m.ReplyDraft(lead_id=customer.id, channel="email", intent="question",
                             meeting_time_request=True,
                             draft_body="Book here https://cal.example/x")
        assert reply_copilot.auto_send_decision(
            db_session, draft, {"allowed_urls": ["https://cal.example/x"]}) == \
            "customer_needs_a_person"
