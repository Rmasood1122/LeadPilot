"""Annual billing -- the independent review's findings on 60b786d (F1-F9 and
the four gaps the founders asked to close). Each test fails on 60b786d.

The reviewer's probes (scratchpad review-ab/test_probe_ab.py) asserted the
DEFECTS; they are ported here with the assertions turned the right way round
(test names keep the probe number).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.config import settings
from app.core import billing_catalog as catalog
from app.db import models as m
from app.integrations import stripe_billing
from app.models.task_error import TaskError
from app.services import billing, pilot_mode

from .test_annual_billing import (  # noqa: F401  (pytest fixtures)
    ANNUAL,
    CONSENT,
    MONTHLY,
    _event,
    _post_webhook,
    _sub,
    annual_on,
    live_stripe,
    webhook_secret,
)

UTC = timezone.utc
REPO = Path(__file__).resolve().parents[1]
YEARLY = {"data": [{"price": {"recurring": {"interval": "year"}}}]}


def _meta(user, model="annual", tier="growth"):
    return {"user_id": str(user.id), "billing_model": model, "tier": tier}


def _task_errors(db, kind):
    return db.execute(select(TaskError).where(TaskError.error_type == kind)).scalars().all()


# --------------------------------------------------------------------------
# F1 -- out-of-order events; Stripe's own state; no stale trial
# --------------------------------------------------------------------------


class TestF1OutOfOrderEvents:
    def test_P1_a_paid_annual_stays_active_when_events_arrive_out_of_order(
            self, client, db_session, test_user, live_stripe, webhook_secret, annual_on):
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="canceled",
             stripe_subscription_id=None, trial_ends_at=datetime.now(UTC) - timedelta(days=60))
        assert client.post("/billing/checkout", json=ANNUAL).status_code == 200
        meta = _meta(test_user)
        now = datetime.now(UTC)
        year_end = now + timedelta(days=365)
        _post_webhook(client, _event("customer.subscription.updated", {
            "id": "sub_paid", "status": "active", "metadata": meta, "items": YEARLY,
            "current_period_end": int(year_end.timestamp())}))
        _post_webhook(client, _event("checkout.session.completed", {
            "mode": "subscription", "customer": "cus_123", "subscription": "sub_paid",
            "metadata": meta}))
        sub = billing.get_subscription(db_session, test_user.id)
        db_session.refresh(sub)
        assert (sub.status, sub.billing_model) == ("active", "annual")
        # (a) the paid-year lock holds
        resp = client.post("/billing/checkout", json=MONTHLY)
        assert resp.status_code == 409
        # (b) the renewal notice is due in the window
        sub.price_unit_amount_cents = 349_000
        kinds = {n["kind"] for n in billing.due_notices(sub, year_end - timedelta(days=20))}
        assert "renewal" in kinds
        # (c) the acknowledgment states no free trial that does not exist
        ack = [n for n in billing.due_notices(sub, now) if n["kind"] == "acknowledgment"][0]
        _, lines = billing.notice_content(sub, ack)
        assert "free trial" not in lines[1] and "next charge" in lines[1]

    def test_completion_takes_the_subscriptions_own_state_from_stripe(
            self, client, db_session, test_user, live_stripe, webhook_secret, annual_on):
        client.post("/billing/checkout", json=ANNUAL)
        end = datetime.now(UTC) + timedelta(days=365)
        live_stripe["set"]("retrieve_subscription", {
            "id": "sub_s", "status": "active", "metadata": _meta(test_user),
            "current_period_end": int(end.timestamp()), "cancel_at_period_end": False,
            "items": {"data": [{"price": {"unit_amount": 349_000, "currency": "usd",
                                          "recurring": {"interval": "year"}}}]}})
        _post_webhook(client, _event("checkout.session.completed", {
            "id": "cs_sub", "mode": "subscription", "customer": "cus_123",
            "subscription": "sub_s", "metadata": _meta(test_user)}))
        sub = billing.get_subscription(db_session, test_user.id)
        db_session.refresh(sub)
        assert sub.status == "active" and sub.price_unit_amount_cents == 349_000
        assert sub.price_interval == "year" and sub.trial_ends_at is None
        assert live_stripe["retrieve_subscription"] == [("sub_s",)]

    def test_a_replacing_subscription_never_inherits_the_old_trial(
            self, client, db_session, test_user, live_stripe, webhook_secret, annual_on):
        old_trial = datetime.now(UTC) + timedelta(days=5)
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="trialing",
             stripe_subscription_id="sub_old", trial_ends_at=old_trial,
             trial_started_at=old_trial - timedelta(days=14), trial_used=True)
        _post_webhook(client, _event("checkout.session.completed", {
            "mode": "subscription", "customer": "cus_1", "subscription": "sub_new",
            "metadata": {**_meta(test_user), "trial_end": ""}}))
        sub = billing.get_subscription(db_session, test_user.id)
        db_session.refresh(sub)
        assert sub.stripe_subscription_id == "sub_new" and sub.status == "active"
        assert sub.trial_ends_at is None and sub.trial_started_at is None
        assert sub.trial_used is True, "the one trial stays used"
        assert billing.had_trial(sub)
        ack = [n for n in billing.due_notices(sub, datetime.now(UTC))
               if n["kind"] == "acknowledgment"]
        assert ack and ack[0]["charge_at"] != old_trial


# --------------------------------------------------------------------------
# F2 -- the paid-annual lock at completion; old sessions expire
# --------------------------------------------------------------------------


class TestF2PaidAnnualAtCompletion:
    def test_P2_a_stale_completion_never_cancels_a_paid_annual_year(
            self, client, db_session, test_user, live_stripe, webhook_secret, annual_on):
        end = datetime.now(UTC) + timedelta(days=300)
        _sub(db_session, test_user, status="active", stripe_subscription_id="sub_paid_annual",
             current_period_end=end)
        test_user.plan = m.PlanTier.GROWTH
        db_session.commit()
        resp = _post_webhook(client, _event("checkout.session.completed", {
            "id": "cs_stale", "mode": "subscription", "customer": "cus_1",
            "subscription": "sub_new", "metadata": _meta(test_user, "monthly", "starter")}))
        assert resp.json()["result"] == "kept_paid_annual"
        assert not live_stripe.get("cancel_subscription_now")
        assert live_stripe["cancel_subscription_at_period_end"] == [("sub_new",)]
        sub = billing.get_subscription(db_session, test_user.id)
        db_session.refresh(sub)
        db_session.refresh(test_user)
        assert (sub.billing_model, sub.stripe_subscription_id) == ("annual", "sub_paid_annual")
        assert test_user.plan is m.PlanTier.GROWTH
        assert "sub_new" in sub.support_note
        assert len(_task_errors(db_session, "BillingNeedsSupport")) == 1
        assert client.get("/billing").json()["subscription"]["needs_support"] is True

    def test_a_card_setup_completing_over_a_paid_annual_is_kept_too(
            self, client, db_session, test_user, live_stripe, webhook_secret):
        _sub(db_session, test_user, status="active", stripe_subscription_id="sub_paid",
             current_period_end=datetime.now(UTC) + timedelta(days=100))
        resp = _post_webhook(client, _event("checkout.session.completed", {
            "mode": "setup", "customer": "cus_1",
            "metadata": _meta(test_user, "pay_per_meeting", "pay_per_meeting")}))
        assert resp.json()["result"] == "kept_paid_annual"
        assert not live_stripe.get("cancel_subscription_now")

    def test_a_new_checkout_expires_the_previous_open_session(
            self, client, db_session, test_user, live_stripe):
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="canceled",
             stripe_subscription_id=None, stripe_checkout_session_id="cs_old")
        assert client.post("/billing/checkout", json=MONTHLY).status_code == 200
        assert live_stripe["expire_checkout_session"] == [("cs_old",)]
        sub = billing.get_subscription(db_session, test_user.id)
        db_session.refresh(sub)
        assert sub.stripe_checkout_session_id == "cs_sub"

    def test_an_already_closed_session_does_not_block_checkout(
            self, client, db_session, test_user, live_stripe, monkeypatch):
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="canceled",
             stripe_subscription_id=None, stripe_checkout_session_id="cs_done")

        def closed(session_id):
            raise stripe_billing.StripeError("stripe HTTP 400: session is complete")

        monkeypatch.setattr(stripe_billing, "expire_checkout_session", closed)
        assert client.post("/billing/checkout", json=MONTHLY).status_code == 200

    def test_stub_mode_never_calls_stripe_to_expire(self, client, db_session, test_user,
                                                    monkeypatch):
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="canceled",
             is_stub=True, stripe_subscription_id=None, stripe_checkout_session_id="cs_old")
        monkeypatch.setattr(stripe_billing, "expire_checkout_session",
                            lambda *a: pytest.fail("stub mode called Stripe"))
        assert client.post("/billing/checkout", json=MONTHLY).status_code == 200


# --------------------------------------------------------------------------
# F3 -- the backend's trial decision drives the disclosure
# --------------------------------------------------------------------------


class TestF3CheckoutTerms:
    def test_a_new_account_is_trial_eligible(self, client):
        terms = client.get("/billing/checkout-terms").json()
        assert terms["trial_eligible"] is True and terms["trial_days"] == 14
        assert terms["pilot_extended"] is False
        end = datetime.fromisoformat(terms["trial_ends_at"])
        assert timedelta(days=13) < end - datetime.now(UTC) <= timedelta(days=14)
        assert terms["first_charge_at"] == terms["trial_ends_at"]
        assert terms["disclosure_version"] == catalog.DISCLOSURE_VERSION

    def test_a_used_trial_means_charged_now(self, client, db_session, test_user):
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="canceled",
             trial_ends_at=datetime.now(UTC) - timedelta(days=40))
        terms = client.get("/billing/checkout-terms").json()
        assert terms["trial_eligible"] is False and terms["trial_days"] == 0
        assert terms["trial_ends_at"] is None
        first = datetime.fromisoformat(terms["first_charge_at"])
        assert abs((first - datetime.now(UTC)).total_seconds()) < 60

    def test_an_active_pilot_extends_it_and_the_checkout_matches(self, client, db_session,
                                                                 test_user):
        pilot = pilot_mode.start_pilot(db_session, test_user,
                                       criteria={"meetings_booked_min": 2},
                                       now=datetime.now(UTC))
        verdict = pilot_mode.verdict_final_at(pilot, pilot_mode.grace(db_session))
        terms = client.get("/billing").json()["checkout_terms"]
        assert terms["pilot_extended"] is True
        assert datetime.fromisoformat(terms["trial_ends_at"]) == verdict
        assert datetime.fromisoformat(terms["pilot_verdict_at"]) == verdict
        client.post("/billing/checkout", json=MONTHLY)
        sub = billing.get_subscription(db_session, test_user.id)
        assert sub.trial_ends_at.replace(tzinfo=UTC) == verdict


# --------------------------------------------------------------------------
# F4 -- cancelling a past-due subscription collects nothing more
# --------------------------------------------------------------------------


class TestF4PastDueCancel:
    def test_P3_cancel_while_past_due_ends_now_and_voids_the_invoice(
            self, client, db_session, test_user, live_stripe):
        _sub(db_session, test_user, status="past_due", stripe_subscription_id="sub_pd",
             current_period_end=datetime.now(UTC) + timedelta(days=360))
        test_user.plan = m.PlanTier.GROWTH
        db_session.commit()
        resp = client.post("/billing/cancel")
        assert resp.status_code == 200 and resp.json()["status"] == "canceled"
        assert live_stripe.get("cancel_subscription_now") == [("sub_pd",)]
        assert live_stripe.get("void_open_invoices") == [("sub_pd",)]
        assert not live_stripe.get("cancel_subscription_at_period_end")
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.FREE

    def test_the_adapter_voids_only_open_invoices(self, monkeypatch):
        sent = []

        def fake(method, path, data=None, **kw):
            sent.append((method, path))
            if method == "GET":
                return {"data": [{"id": "in_1", "status": "open"},
                                 {"id": "in_2", "status": "paid"}]}
            return {}

        monkeypatch.setattr(stripe_billing, "_request", fake)
        assert stripe_billing.void_open_invoices("sub_x") == ["in_1"]
        assert ("POST", "/v1/invoices/in_1/void") in sent
        assert ("POST", "/v1/invoices/in_2/void") not in sent


# --------------------------------------------------------------------------
# F5 -- notices state what Stripe actually bills
# --------------------------------------------------------------------------


class TestF5StripePrice:
    def test_P5_notice_amount_does_not_follow_a_catalog_change(self, db_session, test_user,
                                                               monkeypatch):
        sub = _sub(db_session, test_user,
                   current_period_end=datetime.now(UTC) + timedelta(days=20))
        monkeypatch.setattr(catalog, "ANNUAL_MONTHS_CHARGED", 11)
        (ren,) = [n for n in billing.due_notices(sub, datetime.now(UTC))
                  if n["kind"] == "renewal"]
        assert ren["amount_cents"] == 349_000

    def test_the_webhook_stores_the_stripe_price(self, client, db_session, test_user,
                                                 webhook_secret):
        sub = _sub(db_session, test_user, stripe_subscription_id="sub_p",
                   price_unit_amount_cents=None, price_interval=None)
        _post_webhook(client, _event("customer.subscription.updated", {
            "id": "sub_p", "status": "active", "metadata": _meta(test_user),
            "items": {"data": [{"price": {"unit_amount": 299_000, "currency": "usd",
                                          "recurring": {"interval": "year"}}}]}}))
        db_session.refresh(sub)
        assert (sub.price_unit_amount_cents, sub.price_interval, sub.price_currency) == (
            299_000, "year", "usd")

    def test_an_unknown_live_price_is_fetched_once_or_held(self, db_session, test_user,
                                                           live_stripe, mailbox):
        now = datetime.now(UTC)
        sub = _sub(db_session, test_user, current_period_end=now + timedelta(days=20),
                   price_unit_amount_cents=None, price_interval=None)
        billing.send_renewal_notices(db_session, now=now)
        assert mailbox == [], "no guessed amount is ever emailed"
        rows = db_session.execute(select(m.BillingRenewalNotice)).scalars().all()
        assert {r.status for r in rows} == {"failed"}
        live_stripe["set"]("retrieve_subscription", {
            "id": sub.stripe_subscription_id, "status": "active",
            "items": {"data": [{"price": {"unit_amount": 333_300,
                                          "recurring": {"interval": "year"}}}]}})
        billing.send_renewal_notices(db_session, now=now)
        assert any("$3,333" in msg["subject"] for msg in mailbox)

    def test_stub_rows_use_the_catalog(self):
        row = m.BillingSubscription(billing_model="annual", tier="scale", is_stub=True)
        assert billing.charge_amount(row) == 699_000


# --------------------------------------------------------------------------
# F6 -- trial floor margin
# --------------------------------------------------------------------------


def test_P4_the_trial_floor_has_margin_and_rounds_up(db_session, test_user):
    now = datetime(2026, 10, 11, 12, 0, 0, 900000, tzinfo=UTC)
    pilot_mode.start_pilot(db_session, test_user, criteria={"meetings_booked_min": 2},
                           now=now - timedelta(days=30, hours=12))
    end, pilot_set = billing.trial_end_for(db_session, test_user.id, had_trial=True, now=now)
    sent = int(end.timestamp())
    assert pilot_set
    assert sent >= (now + timedelta(hours=49)).timestamp()


# --------------------------------------------------------------------------
# F7 -- a notice that will not go out is raised to the admins
# --------------------------------------------------------------------------


class TestF7Escalation:
    def test_a_given_up_notice_is_logged_and_listed_once(self, db_session, test_user,
                                                         monkeypatch, caplog):
        from app.services import email_sender

        now = datetime.now(UTC)
        _sub(db_session, test_user, current_period_end=now + timedelta(days=20))
        monkeypatch.setattr(email_sender, "send_email",
                            lambda **kw: (_ for _ in ()).throw(
                                email_sender.EmailSendError("relay down")))
        for _ in range(3):
            billing.send_renewal_notices(db_session, now=now)
        with caplog.at_level(logging.ERROR):
            result = billing.send_renewal_notices(db_session, now=now)
            billing.send_renewal_notices(db_session, now=now)
        assert result["escalated"] >= 1
        assert "has NOT been notified" in caplog.text
        rows = db_session.execute(select(m.BillingRenewalNotice)).scalars().all()
        assert all(r.escalated_at is not None for r in rows)
        assert len(_task_errors(db_session, "RenewalNoticeNotSent")) == len(rows)

    def test_a_notice_stuck_in_sending_is_raised(self, db_session, test_user, caplog):
        now = datetime.now(UTC)
        sub = _sub(db_session, test_user, current_period_end=now + timedelta(days=20))
        (renewal,) = [n for n in billing.due_notices(sub, now) if n["kind"] == "renewal"]
        row = m.BillingRenewalNotice(user_id=test_user.id, subscription_id=sub.id,
                                     kind="renewal", period_key=renewal["period_key"],
                                     status="sending", attempts=1)
        db_session.add(row)
        db_session.commit()
        assert billing.send_notice(db_session, sub, renewal, now) == "skipped"  # in flight
        with caplog.at_level(logging.ERROR):
            assert billing.send_notice(db_session, sub, renewal,
                                       now + timedelta(hours=2)) == "stuck"
        assert "stuck" in caplog.text
        assert len(_task_errors(db_session, "RenewalNoticeNotSent")) == 1


# --------------------------------------------------------------------------
# F8 -- consent recorded at completion, with what was agreed to
# --------------------------------------------------------------------------


class TestF8Consent:
    def test_P6_an_abandoned_checkout_records_no_consent(self, client, db_session, test_user,
                                                         live_stripe, annual_on):
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="active",
             stripe_subscription_id="sub_m")
        client.post("/billing/checkout", json=ANNUAL)
        sub = billing.get_subscription(db_session, test_user.id)
        db_session.refresh(sub)
        assert sub.billing_model == "monthly" and sub.renewal_consent_at is None

    def test_completion_records_version_price_interval_and_session(
            self, client, db_session, test_user, live_stripe, webhook_secret, annual_on):
        client.post("/billing/checkout", json=ANNUAL)
        session_meta = live_stripe["create_subscription_checkout"][0]["session_metadata"]
        assert session_meta["accept_renewal_terms"] == "true"
        _post_webhook(client, _event("checkout.session.completed", {
            "id": "cs_sub", "mode": "subscription", "customer": "cus_123",
            "subscription": "sub_c", "metadata": {**session_meta, **_meta(test_user)}}))
        sub = billing.get_subscription(db_session, test_user.id)
        db_session.refresh(sub)
        assert sub.renewal_consent_at is not None
        assert sub.consent_disclosure_version == catalog.DISCLOSURE_VERSION
        assert (sub.consent_price_cents, sub.consent_interval) == (349_000, "year")
        assert sub.consent_checkout_session_id == "cs_sub"

    def test_a_stub_checkout_records_consent_without_a_session(self, client, db_session,
                                                               test_user):
        client.post("/billing/checkout", json=MONTHLY)
        sub = billing.get_subscription(db_session, test_user.id)
        assert sub.consent_disclosure_version == catalog.DISCLOSURE_VERSION
        assert (sub.consent_price_cents, sub.consent_interval) == (34_900, "month")
        assert sub.consent_checkout_session_id is None


# --------------------------------------------------------------------------
# F9 -- timezone-proof keys, UTC in emails
# --------------------------------------------------------------------------


class TestF9Utc:
    def test_the_same_instant_gives_the_same_key(self):
        utc = datetime(2027, 1, 5, 3, 0, tzinfo=UTC)
        ny = utc.astimezone(timezone(timedelta(hours=-5)))
        naive = utc.replace(tzinfo=None)
        assert billing.period_key(utc) == billing.period_key(ny) == billing.period_key(naive)
        assert billing.period_key(utc) == "2027-01-05T03:00:00Z"

    def test_email_dates_say_utc(self, db_session, test_user):
        sub = _sub(db_session, test_user,
                   current_period_end=datetime(2027, 1, 5, 3, 0, tzinfo=UTC))
        (ren,) = [n for n in billing.due_notices(sub, datetime(2026, 12, 20, tzinfo=UTC))
                  if n["kind"] == "renewal"]
        subject, _ = billing.notice_content(sub, ren)
        assert "January 5, 2027 (UTC)" in subject


# --------------------------------------------------------------------------
# Gaps the founders asked to close
# --------------------------------------------------------------------------


class TestReturningCustomers:
    def test_no_trial_parameter_for_a_used_trial(self, monkeypatch):
        sent = []
        monkeypatch.setattr(stripe_billing, "_request",
                            lambda method, path, data=None, **kw: sent.append(data) or {})
        stripe_billing.create_subscription_checkout(
            customer_id="c", user_id="u", tier=catalog.monthly_tier("growth"), trial_days=0,
            success_url="s", cancel_url="c")
        data = sent[0]["subscription_data"]
        assert "trial_period_days" not in data and "trial_end" not in data

    def test_checkout_for_a_used_trial_sends_none(self, client, db_session, test_user,
                                                  live_stripe):
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="canceled",
             stripe_subscription_id=None, trial_used=True)
        client.post("/billing/checkout", json=MONTHLY)
        (call,) = live_stripe["create_subscription_checkout"]
        assert call["trial_days"] == 0 and call["trial_end"] is None


class TestBasilPeriodEnd:
    @pytest.mark.parametrize("shape", ["top_level", "items"])
    def test_period_end_is_read_from_either_shape(self, client, db_session, test_user,
                                                  webhook_secret, shape):
        sub = _sub(db_session, test_user, stripe_subscription_id="sub_b",
                   current_period_end=None)
        end = int((datetime.now(UTC) + timedelta(days=365)).timestamp())
        item = {"price": {"unit_amount": 349_000, "recurring": {"interval": "year"}}}
        obj = {"id": "sub_b", "status": "active", "metadata": _meta(test_user),
               "items": {"data": [item]}}
        if shape == "top_level":
            obj["current_period_end"] = end
        else:
            item["current_period_end"] = end
        _post_webhook(client, _event("customer.subscription.updated", obj))
        db_session.refresh(sub)
        assert int(sub.current_period_end.replace(tzinfo=UTC).timestamp()) == end


class TestCancelWithoutKey:
    def test_a_real_subscription_is_not_cancelled_locally(self, client, db_session,
                                                          test_user, monkeypatch):
        monkeypatch.setattr(settings, "stripe_secret_key", "")
        monkeypatch.setattr(settings, "app_env", "production")
        sub = _sub(db_session, test_user, stripe_subscription_id="sub_real",
                   current_period_end=datetime.now(UTC) + timedelta(days=200))
        test_user.plan = m.PlanTier.GROWTH
        db_session.commit()
        resp = client.post("/billing/cancel")
        assert resp.status_code == 503
        db_session.refresh(sub)
        db_session.refresh(test_user)
        assert sub.status == "active" and not sub.cancel_at_period_end
        assert test_user.plan is m.PlanTier.GROWTH

    def test_a_stub_row_still_cancels_locally(self, client, db_session, test_user):
        _sub(db_session, test_user, is_stub=True, status="active")
        assert client.post("/billing/cancel").status_code == 200


class TestMonthlyConsent:
    def test_monthly_needs_consent_and_the_current_disclosure(self, client):
        body = {"billing_model": "monthly", "tier": "growth"}
        assert client.post("/billing/checkout", json=body).status_code == 422
        stale = {**body, "accept_renewal_terms": True, "disclosure_version": "1999-01-01"}
        resp = client.post("/billing/checkout", json=stale)
        assert resp.status_code == 409 and "Reload" in resp.json()["detail"]
        assert client.post("/billing/checkout", json=MONTHLY).status_code == 200

    def test_pay_per_meeting_needs_no_renewal_consent(self, client):
        resp = client.post("/billing/checkout", json={"billing_model": "pay_per_meeting"})
        assert resp.status_code == 200

    def test_the_frontend_shows_the_version_the_backend_requires(self):
        text = (REPO / "frontend" / "src" / "lib" / "pricing.ts").read_text(encoding="utf-8")
        match = re.search(r'RENEWAL_DISCLOSURE_VERSION\s*=\s*"([^"]+)"', text)
        assert match and match.group(1) == catalog.DISCLOSURE_VERSION
