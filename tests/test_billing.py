"""Section E — pricing catalog, monthly subscriptions and pay-per-meeting billing.

Stripe is never contacted: stub mode (no key) is exercised as-is, and live
mode replaces the adapter's functions with recorders. Webhooks are signed with
the real Stripe scheme and go through the real endpoint.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.config import settings
from app.core import billing_catalog as catalog
from app.core.plans import PLANS, _PLAN_UPGRADE_PATH
from app.db import models as m
from app.integrations import stripe_billing
from app.services import billing, rbac, revenue_analytics
from tests.conftest import auth_headers

WHSEC = "whsec_test_secret"


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def live_stripe(monkeypatch):
    """Live mode with every Stripe call recorded instead of sent."""
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    calls: dict[str, list] = {}

    def _recorder(name, result):
        def _fn(**kwargs):
            calls.setdefault(name, []).append(kwargs)
            if isinstance(result, Exception):
                raise result
            return result(kwargs) if callable(result) else result
        return _fn

    def install(name, result):
        monkeypatch.setattr(stripe_billing, name, _recorder(name, result))

    install("create_customer", {"id": "cus_123"})
    install("create_subscription_checkout",
            {"id": "cs_sub", "url": "https://checkout.stripe.com/c/pay/cs_sub"})
    install("create_setup_checkout",
            {"id": "cs_setup", "url": "https://checkout.stripe.com/c/pay/cs_setup"})
    install("charge_meeting", {"invoice_id": "in_1", "invoice_item_id": "ii_1",
                               "status": "open"})

    def _cancel_at_end(subscription_id):
        calls.setdefault("cancel_at_period_end", []).append(subscription_id)
        return {}

    def _cancel_now(subscription_id):
        calls.setdefault("cancel_now", []).append(subscription_id)
        return {}

    monkeypatch.setattr(stripe_billing, "cancel_subscription_at_period_end", _cancel_at_end)
    monkeypatch.setattr(stripe_billing, "cancel_subscription_now", _cancel_now)
    calls["install"] = install  # tests can swap a result
    return calls


@pytest.fixture()
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", WHSEC)
    return WHSEC


def _post_webhook(client, payload: dict, secret: str = WHSEC, signature: str | None = None):
    raw = json.dumps(payload).encode()
    header = signature or stripe_billing.sign_webhook(raw, secret)
    return client.post("/webhooks/stripe", content=raw,
                       headers={"Stripe-Signature": header,
                                "Content-Type": "application/json"})


def _event(kind: str, obj: dict) -> dict:
    return {"id": f"evt_{uuid.uuid4().hex[:12]}", "type": kind, "data": {"object": obj}}


@pytest.fixture()
def ppm_account(db_session, test_user):
    sub = m.BillingSubscription(user_id=test_user.id, billing_model="pay_per_meeting",
                                tier="pay_per_meeting", status="active", is_stub=True)
    db_session.add(sub)
    test_user.plan = m.PlanTier.PAY_PER_MEETING
    db_session.commit()
    return sub


@pytest.fixture()
def lead(db_session, verified_strategy):
    row = m.Lead(strategy_id=verified_strategy.id, source="manual", external_id="B1",
                 full_name="Sara Khan", email="sara@acme.com",
                 status=m.LeadStatus.MEETING_BOOKED)
    db_session.add(row)
    db_session.commit()
    return row


def _book(db_session, lead, channel="calendly"):
    db_session.add(m.Outcome(lead_id=lead.id, event=m.OutcomeEvent.BOOKED, channel=channel))
    db_session.commit()


def _meetings(db_session):
    return db_session.execute(select(m.BillableMeeting)).scalars().all()


# --------------------------------------------------------------------------
# catalog
# --------------------------------------------------------------------------


class TestCatalog:
    def test_is_public_and_marks_monthly_recommended(self, anon_client):
        body = anon_client.get("/billing/catalog").json()
        assert body["recommended"] == "monthly"
        assert body["monthly"]["recommended"] is True
        assert body["pay_per_meeting"]["recommended"] is False

    def test_four_monthly_tiers_in_ascending_price(self, anon_client):
        tiers = anon_client.get("/billing/catalog").json()["monthly"]["tiers"]
        assert [t["id"] for t in tiers] == ["starter", "growth", "scale", "enterprise"]
        prices = [t["price_cents"] for t in tiers]
        assert prices == sorted(prices) and len(set(prices)) == 4
        assert all(t["trial_days"] == catalog.TRIAL_DAYS for t in tiers)

    def test_every_advertised_limit_is_an_enforced_plan(self):
        for tier in catalog.MONTHLY_TIERS + [catalog.PAY_PER_MEETING_PLAN]:
            assert tier["plan"] in PLANS
        body = catalog.catalog()
        growth = next(t for t in body["monthly"]["tiers"] if t["id"] == "growth")
        assert growth["limits"]["max_strategies"] == PLANS["growth"]["max_strategies"]

    def test_pay_per_meeting_terms(self):
        ppm = catalog.catalog()["pay_per_meeting"]
        assert ppm["monthly_fee_cents"] == 0
        assert ppm["price_per_meeting_cents"] == 17_900
        assert ppm["grace_hours"] == 48

    def test_upgrade_ladder(self):
        assert [_PLAN_UPGRADE_PATH[k] for k in ("free", "starter", "growth", "scale")] == \
            ["starter", "growth", "scale", "enterprise"]

    def test_billing_routes_are_personal(self):
        assert rbac.is_personal("/billing/checkout")


# --------------------------------------------------------------------------
# checkout — stub mode
# --------------------------------------------------------------------------


class TestStubCheckout:
    def test_monthly_starts_a_trial_and_grants_the_tier(self, client, db_session, test_user):
        resp = client.post("/billing/checkout", json={"billing_model": "monthly",
                                                      "tier": "growth"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mode"] == "stub" and body["checkout_url"] is None
        assert body["subscription"]["status"] == "trialing"
        assert body["subscription"]["is_stub"] is True
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.GROWTH
        sub = billing.get_subscription(db_session, test_user.id)
        trial = sub.trial_ends_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
        assert timedelta(days=13) < trial <= timedelta(days=14)

    def test_the_same_plan_twice_is_a_conflict(self, client):
        body = {"billing_model": "monthly", "tier": "starter"}
        assert client.post("/billing/checkout", json=body).status_code == 200
        assert client.post("/billing/checkout", json=body).status_code == 409

    def test_switching_to_pay_per_meeting(self, client, db_session, test_user):
        client.post("/billing/checkout", json={"billing_model": "monthly", "tier": "scale"})
        resp = client.post("/billing/checkout", json={"billing_model": "pay_per_meeting"})
        assert resp.status_code == 200
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.PAY_PER_MEETING
        assert resp.json()["subscription"]["status"] == "active"

    def test_a_second_monthly_plan_gets_no_second_trial(self, client, db_session, test_user):
        client.post("/billing/checkout", json={"billing_model": "monthly", "tier": "starter"})
        resp = client.post("/billing/checkout", json={"billing_model": "monthly",
                                                      "tier": "growth"})
        assert resp.json()["subscription"]["status"] == "active"

    @pytest.mark.parametrize("body", [{"billing_model": "monthly", "tier": "platinum"},
                                      {"billing_model": "monthly"},
                                      {"billing_model": "lifetime"}])
    def test_invalid_selection(self, client, body):
        assert client.post("/billing/checkout", json=body).status_code == 422

    def test_checkout_needs_a_verified_phone(self, client, db_session, test_user):
        test_user.identity_required = True
        db_session.commit()
        resp = client.post("/billing/checkout", json={"billing_model": "pay_per_meeting"})
        assert resp.status_code == 403 and resp.json()["detail"] == "PHONE_NOT_VERIFIED"

    def test_cancel_in_stub_mode_downgrades_now(self, client, db_session, test_user):
        client.post("/billing/checkout", json={"billing_model": "monthly", "tier": "starter"})
        resp = client.post("/billing/cancel")
        assert resp.status_code == 200 and resp.json()["status"] == "canceled"
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.FREE
        assert client.post("/billing/cancel").status_code == 409

    def test_overview(self, client):
        client.post("/billing/checkout", json={"billing_model": "pay_per_meeting"})
        body = client.get("/billing").json()
        assert body["plan"] == "pay_per_meeting"
        assert body["stub_mode"] is True
        assert body["usage"]["price_per_meeting_cents"] == 17_900


# --------------------------------------------------------------------------
# checkout + webhooks — live mode
# --------------------------------------------------------------------------


class TestLiveCheckoutAndWebhooks:
    def test_monthly_checkout_returns_a_stripe_url_and_changes_nothing_yet(
            self, client, db_session, test_user, live_stripe):
        resp = client.post("/billing/checkout", json={"billing_model": "monthly",
                                                      "tier": "growth"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["checkout_url"].startswith("https://checkout.stripe.com/")
        (call,) = live_stripe["create_subscription_checkout"]
        assert call["tier"]["id"] == "growth" and call["trial_days"] == 14
        assert call["customer_id"] == "cus_123"
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.FREE, "nothing is granted before payment"
        assert billing.get_subscription(db_session, test_user.id).status == "incomplete"

    def test_ppm_checkout_saves_a_card(self, client, live_stripe):
        resp = client.post("/billing/checkout", json={"billing_model": "pay_per_meeting"})
        assert resp.json()["checkout_url"].endswith("cs_setup")
        assert live_stripe["create_setup_checkout"]

    def test_stripe_outage_is_a_502(self, client, live_stripe):
        live_stripe["install"]("create_customer", stripe_billing.StripeError("down"))
        resp = client.post("/billing/checkout", json={"billing_model": "monthly",
                                                      "tier": "starter"})
        assert resp.status_code == 502

    def test_the_webhook_lifecycle(self, client, db_session, test_user, live_stripe,
                                   webhook_secret):
        client.post("/billing/checkout", json={"billing_model": "monthly", "tier": "growth"})
        meta = {"user_id": str(test_user.id), "billing_model": "monthly", "tier": "growth"}

        resp = _post_webhook(client, _event("checkout.session.completed", {
            "mode": "subscription", "customer": "cus_123", "subscription": "sub_1",
            "metadata": meta}))
        assert resp.json()["result"] == "activated"
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.GROWTH

        period_end = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
        _post_webhook(client, _event("customer.subscription.updated", {
            "id": "sub_1", "status": "active", "current_period_end": period_end,
            "cancel_at_period_end": False, "metadata": meta}))
        sub = billing.get_subscription(db_session, test_user.id)
        db_session.refresh(sub)
        assert sub.status == "active" and sub.current_period_end is not None

        _post_webhook(client, _event("invoice.payment_failed", {"subscription": "sub_1"}))
        db_session.refresh(sub)
        assert sub.status == "past_due"
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.GROWTH, "past_due keeps access during dunning"

        _post_webhook(client, _event("customer.subscription.deleted", {"id": "sub_1"}))
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.FREE

    def test_switching_plans_cancels_the_replaced_subscription(
            self, client, db_session, test_user, live_stripe, webhook_secret):
        db_session.add(m.BillingSubscription(user_id=test_user.id, billing_model="monthly",
                                             tier="starter", status="active",
                                             stripe_customer_id="cus_123",
                                             stripe_subscription_id="sub_old"))
        db_session.commit()
        _post_webhook(client, _event("checkout.session.completed", {
            "mode": "subscription", "customer": "cus_123", "subscription": "sub_new",
            "metadata": {"user_id": str(test_user.id), "billing_model": "monthly",
                         "tier": "scale"}}))
        assert live_stripe["cancel_now"] == ["sub_old"]
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.SCALE

    def test_cancel_live_monthly_runs_to_period_end(self, client, db_session, test_user,
                                                    live_stripe):
        db_session.add(m.BillingSubscription(user_id=test_user.id, billing_model="monthly",
                                             tier="growth", status="active",
                                             stripe_subscription_id="sub_9"))
        test_user.plan = m.PlanTier.GROWTH
        db_session.commit()
        resp = client.post("/billing/cancel")
        assert resp.json()["cancel_at_period_end"] is True
        assert live_stripe["cancel_at_period_end"] == ["sub_9"]
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.GROWTH

    def test_unsigned_and_misconfigured_webhooks_are_refused(self, client, monkeypatch):
        monkeypatch.setattr(settings, "stripe_webhook_secret", "")
        assert _post_webhook(client, _event("x", {})).status_code == 503
        monkeypatch.setattr(settings, "stripe_webhook_secret", WHSEC)
        assert _post_webhook(client, _event("x", {}), secret="whsec_wrong").status_code == 401

    def test_a_replayed_event_is_applied_once(self, client, webhook_secret):
        event = _event("invoice.paid", {"subscription": "sub_unknown"})
        assert _post_webhook(client, event).json().get("duplicate") is None
        assert _post_webhook(client, event).json()["duplicate"] is True


class TestWebhookSignature:
    def test_valid_signature(self):
        raw = b'{"id":"evt_1"}'
        assert stripe_billing.verify_webhook(raw, stripe_billing.sign_webhook(raw, WHSEC),
                                             secret=WHSEC)

    def test_tampered_body(self):
        header = stripe_billing.sign_webhook(b'{"id":"evt_1"}', WHSEC)
        assert not stripe_billing.verify_webhook(b'{"id":"evt_2"}', header, secret=WHSEC)

    def test_replay_outside_tolerance(self):
        raw = b"{}"
        old = int(datetime.now(timezone.utc).timestamp()) - 3600
        header = stripe_billing.sign_webhook(raw, WHSEC, timestamp=old)
        assert not stripe_billing.verify_webhook(raw, header, secret=WHSEC)

    def test_form_encoding_matches_stripe_conventions(self):
        pairs = stripe_billing._form({"line_items": [{"price_data": {"unit_amount": 100}}],
                                      "metadata": {"a": "b"}, "flag": True, "skip": None})
        assert ("line_items[0][price_data][unit_amount]", "100") in pairs
        assert ("metadata[a]", "b") in pairs and ("flag", "true") in pairs
        assert all(key != "skip" for key, _ in pairs)

    def test_no_key_means_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "stripe_secret_key", "")
        with pytest.raises(stripe_billing.StripeNotConfigured):
            stripe_billing.create_customer(email="a@b.c", user_id="u")


# --------------------------------------------------------------------------
# metering
# --------------------------------------------------------------------------


class TestMetering:
    def test_a_booked_meeting_is_metered_for_a_ppm_account(self, db_session, ppm_account,
                                                           lead):
        _book(db_session, lead)
        (meeting,) = _meetings(db_session)
        assert meeting.user_id == ppm_account.user_id
        assert meeting.amount_cents == 17_900 and meeting.status == "pending"
        assert meeting.strategy_id == lead.strategy_id and meeting.source == "calendly"
        grace = meeting.charge_after - meeting.occurred_at
        assert grace == timedelta(hours=48)
        outcome = db_session.execute(select(m.Outcome)).scalar_one()
        assert meeting.outcome_id == outcome.id

    def test_once_per_prospect(self, db_session, ppm_account, lead):
        _book(db_session, lead)
        _book(db_session, lead, channel="leadpilot_calendar")
        assert len(_meetings(db_session)) == 1

    def test_monthly_accounts_are_not_metered(self, db_session, test_user, lead):
        db_session.add(m.BillingSubscription(user_id=test_user.id, billing_model="monthly",
                                             tier="growth", status="active"))
        db_session.commit()
        _book(db_session, lead)
        assert _meetings(db_session) == []

    def test_accounts_without_a_plan_are_not_metered(self, db_session, lead):
        _book(db_session, lead)
        assert _meetings(db_session) == []

    def test_a_canceled_ppm_plan_is_not_metered(self, db_session, ppm_account, lead):
        ppm_account.status = "canceled"
        db_session.commit()
        _book(db_session, lead)
        assert _meetings(db_session) == []

    def test_metering_failure_never_breaks_the_booking(self, db_session, ppm_account, lead,
                                                       monkeypatch):
        from app.services import usage_meter

        def _boom(*a, **k):
            raise RuntimeError("meter exploded")

        monkeypatch.setattr(usage_meter, "record_meeting_usage", _boom)
        _book(db_session, lead)
        assert db_session.execute(select(m.Outcome)).scalar_one().event is m.OutcomeEvent.BOOKED

    def test_the_calendly_path_is_metered(self, client, db_session, ppm_account, lead,
                                          monkeypatch):
        """End to end through a real BOOKED writer, not just the ORM."""
        import hashlib
        import hmac
        import time

        lead.status = m.LeadStatus.CONTACTED
        db_session.commit()
        payload = {"event": "invitee.created", "payload": {
            "email": lead.email, "name": "Sara",
            "tracking": {"utm_content": str(ppm_account.user_id)},
            "uri": f"https://api.calendly.com/invitees/{uuid.uuid4()}"}}
        raw = json.dumps(payload).encode()
        ts = str(int(time.time()))
        sig = hmac.new(b"calendly-secret-test", f"{ts}.".encode() + raw,
                       hashlib.sha256).hexdigest()
        resp = client.post("/webhooks/calendly", content=raw, headers={
            "Calendly-Webhook-Signature": f"t={ts},v1={sig}",
            "Content-Type": "application/json"})
        assert resp.status_code == 200 and resp.json().get("matched") is True, resp.text
        assert len(_meetings(db_session)) == 1


# --------------------------------------------------------------------------
# charging sweep, disputes
# --------------------------------------------------------------------------


def _pending(db_session, user, lead, *, hours_ago=49, stub=True):
    now = datetime.now(timezone.utc)
    meeting = m.BillableMeeting(user_id=user.id, lead_id=lead.id,
                                strategy_id=lead.strategy_id, dedupe_key=str(lead.id),
                                source="calendly", amount_cents=17_900, currency="usd",
                                status="pending", occurred_at=now - timedelta(hours=hours_ago),
                                charge_after=now - timedelta(hours=hours_ago - 48),
                                is_stub=stub)
    db_session.add(meeting)
    db_session.commit()
    return meeting


class TestCharging:
    def test_stub_mode_marks_charged_and_says_so(self, db_session, test_user, ppm_account,
                                                 lead):
        meeting = _pending(db_session, test_user, lead)
        result = billing.charge_due_meetings(db_session)
        assert result == {"processed": 1, "charged_stub": 1}
        db_session.refresh(meeting)
        assert meeting.status == "charged" and meeting.is_stub is True

    def test_meetings_inside_the_grace_window_wait(self, db_session, test_user, ppm_account,
                                                   lead):
        _pending(db_session, test_user, lead, hours_ago=2)
        assert billing.charge_due_meetings(db_session) == {"processed": 0}

    def test_a_cancelled_meeting_is_waived(self, db_session, test_user, ppm_account, lead):
        lead.status = m.LeadStatus.REPLIED      # what a Calendly cancellation writes
        db_session.commit()
        meeting = _pending(db_session, test_user, lead)
        billing.charge_due_meetings(db_session)
        db_session.refresh(meeting)
        assert meeting.status == "waived"

    def test_live_charge(self, db_session, test_user, ppm_account, lead, live_stripe):
        ppm_account.is_stub, ppm_account.stripe_customer_id = False, "cus_123"
        db_session.commit()
        meeting = _pending(db_session, test_user, lead, stub=False)
        assert billing.charge_due_meetings(db_session)["charged"] == 1
        db_session.refresh(meeting)
        assert (meeting.status, meeting.stripe_invoice_id) == ("charged", "in_1")
        (call,) = live_stripe["charge_meeting"]
        assert call["amount_cents"] == 17_900 and call["meeting_id"] == str(meeting.id)
        assert "Sara" not in call["description"], "no prospect PII on an invoice line"

    def test_live_charge_failure(self, db_session, test_user, ppm_account, lead, live_stripe):
        ppm_account.is_stub, ppm_account.stripe_customer_id = False, "cus_123"
        db_session.commit()
        live_stripe["install"]("charge_meeting", stripe_billing.StripeError("card declined"))
        meeting = _pending(db_session, test_user, lead, stub=False)
        billing.charge_due_meetings(db_session)
        db_session.refresh(meeting)
        assert meeting.status == "failed" and "declined" in meeting.failure_reason

    def test_invoice_webhooks_settle_a_meeting(self, client, db_session, test_user,
                                               ppm_account, lead, webhook_secret):
        meeting = _pending(db_session, test_user, lead, stub=False)
        meeting.status = "charged"
        db_session.commit()
        _post_webhook(client, _event("invoice.payment_failed", {
            "metadata": {"billable_meeting_id": str(meeting.id)}}))
        db_session.refresh(meeting)
        assert meeting.status == "failed"


class TestDisputes:
    @pytest.fixture()
    def admin(self, db_session):
        user = m.User(email="billing-admin@leadpilot.dev", is_admin=True, email_verified=True)
        db_session.add(user)
        db_session.commit()
        return user

    def test_dispute_inside_the_grace_window(self, client, db_session, test_user,
                                             ppm_account, lead):
        meeting = _pending(db_session, test_user, lead, hours_ago=1)
        resp = client.post(f"/billing/meetings/{meeting.id}/dispute",
                           json={"reason": "They cancelled by email"})
        assert resp.status_code == 200 and resp.json()["status"] == "disputed"
        # A disputed meeting is not charged by the sweep.
        meeting.charge_after = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()
        assert billing.charge_due_meetings(db_session) == {"processed": 0}

    def test_no_dispute_after_the_grace_window(self, client, db_session, test_user,
                                               ppm_account, lead):
        meeting = _pending(db_session, test_user, lead)
        assert client.post(f"/billing/meetings/{meeting.id}/dispute",
                           json={"reason": "late"}).status_code == 409

    def test_another_accounts_meeting_is_404(self, client, db_session, lead):
        other = m.User(email="someone@else.com", email_verified=True)
        db_session.add(other)
        db_session.commit()
        meeting = _pending(db_session, other, lead, hours_ago=1)
        assert client.post(f"/billing/meetings/{meeting.id}/dispute",
                           json={"reason": "not mine"}).status_code == 404

    def test_admin_resolution(self, client, db_session, test_user, ppm_account, lead, admin):
        meeting = _pending(db_session, test_user, lead, hours_ago=1)
        client.post(f"/billing/meetings/{meeting.id}/dispute", json={"reason": "no-show"})
        assert client.post(f"/admin/billing/meetings/{meeting.id}/resolve",
                           json={"decision": "waive"}).status_code == 403
        resp = client.post(f"/admin/billing/meetings/{meeting.id}/resolve",
                           json={"decision": "charge", "note": "they attended"},
                           headers=auth_headers(admin))
        assert resp.status_code == 200 and resp.json()["status"] == "pending"
        assert billing.charge_due_meetings(db_session)["charged_stub"] == 1

    def test_meetings_list(self, client, db_session, test_user, ppm_account, lead):
        _pending(db_session, test_user, lead)
        rows = client.get("/billing/meetings").json()
        assert len(rows) == 1 and rows[0]["amount_cents"] == 17_900
        assert client.get("/billing/meetings?status=charged").json() == []


# --------------------------------------------------------------------------
# revenue analytics
# --------------------------------------------------------------------------


def test_meeting_fees_are_a_campaign_cost(db_session, test_user, ppm_account, lead):
    _pending(db_session, test_user, lead, hours_ago=1)
    waived = m.Lead(strategy_id=lead.strategy_id, source="manual", external_id="B2",
                    email="w@acme.com", status=m.LeadStatus.REPLIED)
    db_session.add(waived)
    db_session.commit()
    row = _pending(db_session, test_user, waived, hours_ago=1)
    row.status = "waived"
    db_session.commit()

    today = datetime.now(timezone.utc).date()
    report = revenue_analytics.report(db_session, test_user.id, today - timedelta(days=7),
                                      today + timedelta(days=1))
    (campaign,) = [c for c in report["campaigns"] if c["strategy_id"] == str(lead.strategy_id)]
    assert campaign["platform_cost_cents"] == 17_900
    assert campaign["total_cost_cents"] >= 17_900
    assert report["notes"]["platform_fee_usd_cents"] == 17_900


def test_the_charge_sweep_is_scheduled_and_routed():
    from app.workers import billing_tasks  # noqa: F401
    from app.workers.celery_app import celery_app

    entry = celery_app.conf.beat_schedule["charge-due-meetings"]
    assert entry["task"] == "app.workers.billing_tasks.charge_due_meetings"
    route = celery_app.amqp.router.route({}, entry["task"])
    assert route["queue"].name == "default"
