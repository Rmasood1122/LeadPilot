"""Annual billing (docs/features/annual-billing.md).

What must hold:
  * the catalog offers annual only with `annual_billing_enabled` on; the
    annual price is monthly x ANNUAL_MONTHS_CHARGED, defined in ONE place,
    with the monthly tier's limits;
  * annual checkout: flag off 409, consent required (422) and stored; stub
    and live semantics mirror monthly (trial once, cancel at period end live,
    now in stub); Stripe interval "year"; a PAID annual year cannot be
    switched online (no refund path), a trialing one can;
  * an ACTIVE F09 pilot pushes a new subscription's trial to the verdict
    (monthly and annual, with or without a previous trial) -- never a charge
    during a pilot;
  * NEVER AUTOMATIC: monthly renewals, metadata-less events, the flag, and a
    pilot ending leave a monthly row monthly;
  * auto-renewal notices: acknowledgment once, trial-ending 7 days ahead,
    renewal 30 days ahead, once per renewal (idempotent), none for stub /
    cancelling / monthly 14-day trials, retried and capped, each naming the
    amount, the date and the online cancel path;
  * tenancy; Celery routing and schedule.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.core import billing_catalog as catalog
from app.core.plans import PLANS
from app.db import models as m
from app.integrations import stripe_billing
from app.services import billing, pilot_mode, system_settings

UTC = timezone.utc
WHSEC = "whsec_test_secret"
REPO = Path(__file__).resolve().parents[1]
CONSENT = {"accept_renewal_terms": True, "disclosure_version": catalog.DISCLOSURE_VERSION}
ANNUAL = {"billing_model": "annual", "tier": "growth", **CONSENT}
MONTHLY = {"billing_model": "monthly", "tier": "growth", **CONSENT}


# --------------------------------------------------------------------------
# fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture()
def annual_on(db_session):
    system_settings.set(db_session, billing.ANNUAL_FLAG, True)


@pytest.fixture()
def live_stripe(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
    calls: dict[str, list] = {}

    def _rec(name, result):
        def _fn(*args, **kwargs):
            calls.setdefault(name, []).append(kwargs or args)
            return result
        monkeypatch.setattr(stripe_billing, name, _fn)

    _rec("create_customer", {"id": "cus_123"})
    _rec("create_subscription_checkout", {"id": "cs_sub", "url": "https://checkout.stripe.com/x"})
    _rec("create_setup_checkout", {"id": "cs_setup", "url": "https://checkout.stripe.com/y"})
    _rec("cancel_subscription_at_period_end", {})
    _rec("cancel_subscription_now", {})
    _rec("retrieve_subscription", {})
    _rec("expire_checkout_session", {})
    _rec("void_open_invoices", ["in_open_1"])

    def set_result(name, result):
        _rec(name, result)

    calls["set"] = set_result
    return calls


@pytest.fixture()
def webhook_secret(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", WHSEC)


def _post_webhook(client, payload: dict):
    raw = json.dumps(payload).encode()
    return client.post("/webhooks/stripe", content=raw,
                       headers={"Stripe-Signature": stripe_billing.sign_webhook(raw, WHSEC),
                                "Content-Type": "application/json"})


def _event(kind: str, obj: dict) -> dict:
    return {"id": f"evt_{uuid.uuid4().hex[:12]}", "type": kind, "data": {"object": obj}}


def _sub(db, user, **kw) -> m.BillingSubscription:
    values = {"billing_model": "annual", "tier": "growth", "status": "active",
              "is_stub": False, "stripe_customer_id": "cus_1",
              "stripe_subscription_id": f"sub_{uuid.uuid4().hex[:8]}"}
    if kw.get("billing_model", "annual") in ("annual", "monthly"):
        # What Stripe bills, as the subscription webhook stores it.
        model, tier = kw.get("billing_model", "annual"), kw.get("tier", "growth")
        values["price_unit_amount_cents"] = catalog.price_cents(model, tier)
        values["price_interval"] = catalog.interval_for(model)
    values.update(kw)
    row = m.BillingSubscription(user_id=user.id, **values)
    db.add(row)
    db.commit()
    return row


def _aware(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=UTC)


def _active_pilot(db, user, now=None):
    return pilot_mode.start_pilot(db, user, criteria={"meetings_booked_min": 2},
                                  now=now or datetime.now(UTC))


def _notices(db, user=None):
    query = select(m.BillingRenewalNotice)
    if user is not None:
        query = query.where(m.BillingRenewalNotice.user_id == user.id)
    return db.execute(query).scalars().all()


# --------------------------------------------------------------------------
# catalog
# --------------------------------------------------------------------------


class TestCatalog:
    def test_flag_is_off_by_default_and_hides_annual(self, anon_client):
        assert system_settings.DEFAULTS[billing.ANNUAL_FLAG][0] is False
        body = anon_client.get("/billing/catalog").json()
        assert "annual" not in body and body["annual_available"] is False
        assert body["recommended"] == "monthly"

    def test_annual_price_is_monthly_times_the_constant(self, anon_client, annual_on):
        body = anon_client.get("/billing/catalog").json()
        assert body["annual_available"] is True
        annual = {t["id"]: t for t in body["annual"]["tiers"]}
        monthly = {t["id"]: t for t in body["monthly"]["tiers"]}
        assert list(annual) == ["starter", "growth", "scale", "enterprise"]
        for tier_id, tier in annual.items():
            m_price = monthly[tier_id]["price_cents"]
            assert tier["annual_price_cents"] == m_price * catalog.ANNUAL_MONTHS_CHARGED
            assert tier["savings_cents"] == m_price * 12 - tier["annual_price_cents"]
            assert tier["limits"] == monthly[tier_id]["limits"], "limits are identical"
            assert tier["plan"] == monthly[tier_id]["plan"]
        assert annual["growth"]["annual_price_cents"] == 349_000
        assert annual["starter"]["monthly_equivalent_cents"] == 12_417   # 1490/12
        assert body["annual"]["months_charged"] == 10 == catalog.ANNUAL_MONTHS_CHARGED

    def test_annual_grants_the_same_plan_as_monthly(self):
        for tier in catalog.MONTHLY_TIERS:
            assert catalog.plan_for("annual", tier["id"]) == catalog.plan_for("monthly", tier["id"])
            assert catalog.plan_for("annual", tier["id"]) in PLANS
        assert catalog.plan_for("annual", "pay_per_meeting") is None
        assert catalog.interval_for("annual") == "year"
        assert catalog.interval_for("monthly") == "month"

    def test_the_multiplier_is_defined_in_one_place(self):
        hits = []
        for path in (REPO / "app").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^\s*ANNUAL_MONTHS_CHARGED\s*=", text, flags=re.MULTILINE):
                hits.append(path.relative_to(REPO).as_posix())
        assert hits == ["app/core/billing_catalog.py"]

    def test_notice_windows_sit_inside_the_cited_statutory_windows(self):
        """CA ARL 15-45 days and NY GOL 5-903 15-30 days (renewal); CA ARL
        3-21 days (long trials). Needs founder/legal confirmation."""
        assert 15 <= catalog.RENEWAL_NOTICE_DAYS <= 30
        assert 3 <= catalog.TRIAL_NOTICE_DAYS <= 21
        assert catalog.NOTICE_LATE_DAYS == 15


# --------------------------------------------------------------------------
# checkout
# --------------------------------------------------------------------------


class TestCheckout:
    def test_flag_off_refuses_annual(self, client):
        resp = client.post("/billing/checkout", json=ANNUAL)
        assert resp.status_code == 409
        assert "not offered" in resp.json()["detail"]

    def test_consent_is_required_and_stored(self, client, db_session, test_user, annual_on):
        resp = client.post("/billing/checkout", json={**ANNUAL, "accept_renewal_terms": False})
        assert resp.status_code == 422
        assert billing.get_subscription(db_session, test_user.id) is None
        resp = client.post("/billing/checkout", json=ANNUAL)
        assert resp.status_code == 200, resp.text
        sub = billing.get_subscription(db_session, test_user.id)
        assert sub.renewal_consent_at is not None

    def test_stub_annual_first_checkout_is_a_14_day_trial(self, client, db_session, test_user,
                                                          annual_on):
        body = client.post("/billing/checkout", json=ANNUAL).json()
        assert body["mode"] == "stub"
        assert body["subscription"]["billing_model"] == "annual"
        assert body["subscription"]["status"] == "trialing"
        assert body["subscription"]["price_cents"] == 349_000
        assert body["subscription"]["interval"] == "year"
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.GROWTH
        sub = billing.get_subscription(db_session, test_user.id)
        trial = _aware(sub.trial_ends_at) - datetime.now(UTC)
        assert timedelta(days=13) < trial <= timedelta(days=14)
        assert sub.trial_started_at is not None

    def test_stub_annual_after_a_trial_is_active_for_a_year(self, client, db_session,
                                                            test_user, annual_on):
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="trialing",
             is_stub=True, trial_ends_at=datetime.now(UTC) + timedelta(days=3))
        test_user.plan = m.PlanTier.STARTER
        db_session.commit()
        body = client.post("/billing/checkout", json=ANNUAL).json()
        assert body["subscription"]["status"] == "active"
        sub = billing.get_subscription(db_session, test_user.id)
        left = _aware(sub.current_period_end) - datetime.now(UTC)
        assert timedelta(days=364) < left <= timedelta(days=365)

    def test_live_annual_checkout_bills_yearly(self, client, db_session, test_user,
                                               annual_on, live_stripe):
        resp = client.post("/billing/checkout", json=ANNUAL)
        assert resp.status_code == 200, resp.text
        (call,) = live_stripe["create_subscription_checkout"]
        assert call["interval"] == "year" and call["billing_model"] == "annual"
        assert call["unit_amount_cents"] == 349_000
        assert call["trial_days"] == 14 and call["trial_end"] is None
        assert call["price_id"] is None
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.FREE, "nothing granted before payment"

    def test_a_configured_annual_price_id_is_used(self, client, annual_on, live_stripe,
                                                  monkeypatch):
        monkeypatch.setattr(settings, "stripe_price_growth_annual", "price_growth_year")
        monkeypatch.setattr(settings, "stripe_price_growth", "price_growth_month")
        client.post("/billing/checkout", json=ANNUAL)
        assert live_stripe["create_subscription_checkout"][0]["price_id"] == "price_growth_year"

    def test_the_adapter_sends_a_year_interval_and_annual_metadata(self, monkeypatch):
        sent = []
        monkeypatch.setattr(stripe_billing, "_request",
                            lambda method, path, data=None, **kw: sent.append(data) or {})
        stripe_billing.create_subscription_checkout(
            customer_id="cus", user_id="u", tier=catalog.monthly_tier("scale"),
            trial_days=14, success_url="s", cancel_url="c", billing_model="annual",
            interval="year", unit_amount_cents=catalog.annual_price_cents("scale"))
        data = sent[0]
        price = data["line_items"][0]["price_data"]
        assert price["recurring"] == {"interval": "year"}
        assert price["unit_amount"] == 699_000
        assert "(annual)" in price["product_data"]["name"]
        assert data["metadata"]["billing_model"] == "annual"
        assert data["subscription_data"]["trial_period_days"] == 14
        assert "trial_end" not in data["subscription_data"]
        with pytest.raises(ValueError):
            stripe_billing.create_subscription_checkout(
                customer_id="cus", user_id="u", tier=catalog.monthly_tier("scale"),
                trial_days=0, success_url="s", cancel_url="c", interval="week")

    def test_a_paid_annual_year_cannot_be_switched_online(self, client, db_session, test_user,
                                                          annual_on):
        _sub(db_session, test_user, status="active", is_stub=True,
             current_period_end=datetime.now(UTC) + timedelta(days=200))
        for body in ({"billing_model": "monthly", "tier": "scale", **CONSENT},
                     {"billing_model": "pay_per_meeting"},
                     {**ANNUAL, "tier": "scale"}):
            resp = client.post("/billing/checkout", json=body)
            assert resp.status_code == 409, body
            assert "contact support" in resp.json()["detail"]
        assert client.post("/billing/checkout", json=ANNUAL).status_code == 409   # same plan

    def test_a_cancelling_paid_annual_year_is_still_locked(self, client, db_session, test_user,
                                                           annual_on):
        _sub(db_session, test_user, status="active", is_stub=True, cancel_at_period_end=True,
             current_period_end=datetime.now(UTC) + timedelta(days=100))
        resp = client.post("/billing/checkout", json={"billing_model": "monthly",
                                                      "tier": "growth", **CONSENT})
        assert resp.status_code == 409 and "paid until" in resp.json()["detail"]

    def test_a_trialing_annual_plan_can_switch(self, client, db_session, test_user, annual_on):
        client.post("/billing/checkout", json=ANNUAL)
        resp = client.post("/billing/checkout", json={"billing_model": "monthly",
                                                      "tier": "growth", **CONSENT})
        assert resp.status_code == 200
        assert resp.json()["subscription"]["billing_model"] == "monthly"

    def test_cancel_live_annual_runs_to_period_end(self, client, db_session, test_user,
                                                   live_stripe):
        end = datetime.now(UTC) + timedelta(days=300)
        sub = _sub(db_session, test_user, stripe_subscription_id="sub_y",
                   current_period_end=end)
        test_user.plan = m.PlanTier.GROWTH
        db_session.commit()
        resp = client.post("/billing/cancel")
        assert resp.status_code == 200 and resp.json()["cancel_at_period_end"] is True
        assert live_stripe["cancel_subscription_at_period_end"] == [("sub_y",)]
        db_session.refresh(test_user)
        db_session.refresh(sub)
        assert test_user.plan is m.PlanTier.GROWTH and sub.status == "active"

    def test_cancel_stub_annual_ends_now(self, client, db_session, test_user, annual_on):
        client.post("/billing/checkout", json=ANNUAL)
        resp = client.post("/billing/cancel")
        assert resp.json()["status"] == "canceled"
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.FREE

    def test_flag_off_later_keeps_an_existing_annual_plan_working(
            self, client, db_session, test_user, annual_on):
        client.post("/billing/checkout", json=ANNUAL)
        system_settings.set(db_session, billing.ANNUAL_FLAG, False)
        body = client.get("/billing").json()
        assert body["subscription"]["billing_model"] == "annual"
        assert body["plan"] == "growth"
        assert client.post("/billing/cancel").status_code == 200


# --------------------------------------------------------------------------
# trial vs pilot
# --------------------------------------------------------------------------


class TestPilotTrial:
    @pytest.mark.parametrize("body", [{"billing_model": "monthly", "tier": "growth", **CONSENT}, ANNUAL])
    def test_stub_trial_runs_to_the_pilot_verdict(self, client, db_session, test_user,
                                                  annual_on, body):
        pilot = _active_pilot(db_session, test_user)
        verdict = pilot_mode.verdict_final_at(pilot, pilot_mode.grace(db_session))
        resp = client.post("/billing/checkout", json=body)
        assert resp.status_code == 200, resp.text
        sub = billing.get_subscription(db_session, test_user.id)
        assert sub.status == "trialing"
        assert _aware(sub.trial_ends_at) == verdict
        assert _aware(sub.trial_ends_at) > datetime.now(UTC) + timedelta(days=14)

    @pytest.mark.parametrize("body", [{"billing_model": "monthly", "tier": "growth", **CONSENT}, ANNUAL])
    def test_live_trial_end_is_the_pilot_verdict(self, client, db_session, test_user,
                                                 annual_on, live_stripe, body):
        pilot = _active_pilot(db_session, test_user)
        verdict = pilot_mode.verdict_final_at(pilot, pilot_mode.grace(db_session))
        client.post("/billing/checkout", json=body)
        (call,) = live_stripe["create_subscription_checkout"]
        assert call["trial_end"] == int(verdict.timestamp())

    def test_no_charge_during_a_pilot_even_after_a_used_trial(self, client, db_session,
                                                              test_user, live_stripe):
        _sub(db_session, test_user, billing_model="monthly", tier="starter", status="canceled",
             trial_ends_at=datetime.now(UTC) - timedelta(days=60))
        pilot = _active_pilot(db_session, test_user)
        verdict = pilot_mode.verdict_final_at(pilot, pilot_mode.grace(db_session))
        client.post("/billing/checkout", json={"billing_model": "monthly", "tier": "growth", **CONSENT})
        (call,) = live_stripe["create_subscription_checkout"]
        assert call["trial_days"] == 0
        assert call["trial_end"] == int(verdict.timestamp()), "trial pushed past the verdict"

    def test_a_trial_is_never_shorter_than_stripes_minimum(self, db_session, test_user):
        now = datetime.now(UTC)
        # A pilot whose verdict is 10 hours away (started ~31 days ago).
        pilot = _active_pilot(db_session, test_user, now=now - timedelta(days=30))
        pilot.ends_at = now - timedelta(hours=14)        # grace 24h -> verdict in 10h
        db_session.commit()
        end, pilot_set = billing.trial_end_for(db_session, test_user.id, had_trial=True,
                                               now=now)
        assert pilot_set is True
        # F6: 48 h (Stripe's minimum) + 1 h margin, rounded UP to a second.
        assert billing.TRIAL_FLOOR == timedelta(hours=49)
        assert end.timestamp() == int(end.timestamp())
        assert now + billing.TRIAL_FLOOR <= end < now + billing.TRIAL_FLOOR + timedelta(seconds=1)

    def test_no_pilot_or_an_ended_pilot_means_the_normal_trial(self, db_session, test_user):
        now = datetime.now(UTC)
        assert billing.trial_end_for(db_session, test_user.id, had_trial=False, now=now) == (
            now + timedelta(days=catalog.TRIAL_DAYS), False)
        assert billing.trial_end_for(db_session, test_user.id, had_trial=True,
                                     now=now) == (None, False)
        pilot = _active_pilot(db_session, test_user)
        pilot_mode.end_pilot(db_session, pilot, reason="ended_early", now=now)
        assert billing.trial_end_for(db_session, test_user.id, had_trial=False, now=now) == (
            now + timedelta(days=catalog.TRIAL_DAYS), False)

    def test_another_accounts_pilot_does_not_count(self, db_session, test_user):
        other = m.User(email="other-annual@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        _active_pilot(db_session, other)
        assert billing.pilot_trial_end(db_session, test_user.id, datetime.now(UTC)) is None

    def test_pay_per_meeting_is_untouched_by_a_pilot(self, client, db_session, test_user):
        _active_pilot(db_session, test_user)
        body = client.post("/billing/checkout", json={"billing_model": "pay_per_meeting"}).json()
        assert body["subscription"]["status"] == "active"
        assert body["subscription"]["trial_ends_at"] is None


# --------------------------------------------------------------------------
# never automatic
# --------------------------------------------------------------------------


class TestNeverAutoConvert:
    def test_monthly_renewal_events_keep_monthly(self, client, db_session, test_user,
                                                 webhook_secret, annual_on):
        sub = _sub(db_session, test_user, billing_model="monthly", stripe_subscription_id="sub_m")
        meta = {"user_id": str(test_user.id), "billing_model": "monthly", "tier": "growth"}
        for days in (30, 60, 90):
            end = int((datetime.now(UTC) + timedelta(days=days)).timestamp())
            _post_webhook(client, _event("customer.subscription.updated", {
                "id": "sub_m", "status": "active", "current_period_end": end,
                "metadata": meta,
                "items": {"data": [{"price": {"recurring": {"interval": "month"}}}]}}))
            _post_webhook(client, _event("invoice.paid", {"subscription": "sub_m"}))
        db_session.refresh(sub)
        assert sub.billing_model == "monthly"

    def test_an_event_without_billing_model_metadata_stays_monthly(
            self, client, db_session, test_user, webhook_secret):
        sub = _sub(db_session, test_user, billing_model="monthly", stripe_subscription_id="sub_o")
        _post_webhook(client, _event("customer.subscription.updated", {
            "id": "sub_o", "status": "active", "metadata": {"tier": "growth"}}))
        db_session.refresh(sub)
        assert sub.billing_model == "monthly"

    def test_turning_the_flag_on_changes_no_subscription(self, db_session, test_user):
        sub = _sub(db_session, test_user, billing_model="monthly")
        system_settings.set(db_session, billing.ANNUAL_FLAG, True)
        billing.send_renewal_notices(db_session)
        db_session.refresh(sub)
        assert sub.billing_model == "monthly"

    def test_a_pilot_ending_leaves_a_monthly_plan_monthly(self, db_session, test_user):
        system_settings.set(db_session, pilot_mode.FLAG, True)
        system_settings.set(db_session, billing.ANNUAL_FLAG, True)
        sub = _sub(db_session, test_user, billing_model="monthly", tier="starter")
        now = datetime.now(UTC)
        pilot = _active_pilot(db_session, test_user, now=now)
        pilot_mode.sweep(db_session, now=now + timedelta(days=40))
        db_session.refresh(pilot)
        db_session.refresh(sub)
        assert pilot.status == "ended"
        assert (sub.billing_model, sub.tier, sub.status) == ("monthly", "starter", "active")


# --------------------------------------------------------------------------
# webhooks
# --------------------------------------------------------------------------


class TestAnnualWebhooks:
    def test_lifecycle(self, client, db_session, test_user, live_stripe, webhook_secret,
                       annual_on):
        client.post("/billing/checkout", json=ANNUAL)
        meta = {"user_id": str(test_user.id), "billing_model": "annual", "tier": "growth"}
        # The session echoes the metadata the checkout wrote (consent + trial).
        session_meta = live_stripe["create_subscription_checkout"][0]["session_metadata"]
        resp = _post_webhook(client, _event("checkout.session.completed", {
            "id": "cs_sub", "mode": "subscription", "customer": "cus_123",
            "subscription": "sub_a", "metadata": {**session_meta, **meta}}))
        assert resp.json()["result"] == "activated"
        sub = billing.get_subscription(db_session, test_user.id)
        db_session.refresh(sub)
        assert (sub.billing_model, sub.status) == ("annual", "trialing")

        now = datetime.now(UTC)
        trial_start, trial_end = now, now + timedelta(days=14)
        year_end = trial_end + timedelta(days=365)
        yearly = {"data": [{"price": {"recurring": {"interval": "year"}}}]}
        _post_webhook(client, _event("customer.subscription.updated", {
            "id": "sub_a", "status": "active", "metadata": meta, "items": yearly,
            "trial_start": int(trial_start.timestamp()),
            "trial_end": int(trial_end.timestamp()),
            "current_period_end": int(year_end.timestamp())}))
        db_session.refresh(sub)
        assert sub.billing_model == "annual" and sub.status == "active"
        assert abs((_aware(sub.trial_started_at) - trial_start).total_seconds()) < 2
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.GROWTH

        # Renewal: a new period end -> next year's notice keys on it.
        next_end = year_end + timedelta(days=365)
        _post_webhook(client, _event("customer.subscription.updated", {
            "id": "sub_a", "status": "active", "metadata": meta, "items": yearly,
            "current_period_end": int(next_end.timestamp())}))
        db_session.refresh(sub)
        assert abs((_aware(sub.current_period_end) - next_end).total_seconds()) < 2

        _post_webhook(client, _event("customer.subscription.deleted", {"id": "sub_a"}))
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.FREE

    def test_the_price_interval_wins_over_metadata(self):
        yearly = {"items": {"data": [{"price": {"recurring": {"interval": "year"}}}]},
                  "metadata": {"billing_model": "monthly"}}
        monthly = {"items": {"data": [{"price": {"recurring": {"interval": "month"}}}]},
                   "metadata": {"billing_model": "annual"}}
        assert billing._model_of(yearly) == "annual"
        assert billing._model_of(monthly) == "monthly"
        assert billing._model_of({"metadata": {"billing_model": "annual"}}) == "annual"
        assert billing._model_of({}) == "monthly"


# --------------------------------------------------------------------------
# notices
# --------------------------------------------------------------------------


class TestNotices:
    def test_renewal_due_30_days_ahead_not_31(self, db_session, test_user):
        now = datetime(2026, 10, 11, 15, 10, tzinfo=UTC)
        sub = _sub(db_session, test_user, current_period_end=now + timedelta(days=31))
        kinds = {n["kind"] for n in billing.due_notices(sub, now)}
        assert kinds == {"acknowledgment"}
        kinds = {n["kind"] for n in billing.due_notices(sub, now + timedelta(days=1))}
        assert kinds == {"acknowledgment", "renewal"}

    def test_sweep_sends_once_per_renewal(self, db_session, test_user, mailbox):
        now = datetime(2026, 10, 11, 15, 10, tzinfo=UTC)
        end = now + timedelta(days=29)
        sub = _sub(db_session, test_user, current_period_end=end)
        assert billing.send_renewal_notices(db_session, now=now)["sent"] == 2   # ack + renewal
        for _ in range(3):
            assert billing.send_renewal_notices(db_session, now=now + timedelta(days=1))[
                "sent"] == 0
        renewal = [n for n in _notices(db_session) if n.kind == "renewal"]
        assert len(renewal) == 1 and renewal[0].status == "sent"
        assert renewal[0].days_before == 29 and renewal[0].amount_cents == 349_000
        mails = [msg for msg in mailbox if "renews on" in msg["subject"]]
        assert len(mails) == 1
        mail = mails[0]
        assert mail["to"] == test_user.email
        assert "$3,490" in mail["subject"] and end.strftime("%B") in mail["subject"]
        assert "/profile" in mail["text"] and "Cancel plan" in mail["text"]
        assert "renews automatically" in mail["text"]

        # The renewal happened: a new period gets its own notice next year.
        sub.current_period_end = end + timedelta(days=365)
        db_session.commit()
        later = end + timedelta(days=340)
        assert billing.send_renewal_notices(db_session, now=later)["sent"] == 1
        assert len([n for n in _notices(db_session) if n.kind == "renewal"]) == 2

    def test_acknowledgment_once_per_subscription(self, db_session, test_user, mailbox):
        now = datetime.now(UTC)
        sub = _sub(db_session, test_user, status="trialing",
                   trial_ends_at=now + timedelta(days=14),
                   current_period_end=now + timedelta(days=14))
        billing.send_renewal_notices(db_session, now=now)
        billing.send_renewal_notices(db_session, now=now)
        acks = [n for n in _notices(db_session) if n.kind == "acknowledgment"]
        assert len(acks) == 1
        text = next(msg for msg in mailbox if "renewal terms" in msg["subject"])["text"]
        assert "free trial ends" in text and "every year" in text and "Cancel plan" in text
        assert sub.id == acks[0].subscription_id

    def test_no_notice_for_cancelling_canceled_monthly_or_stub(self, db_session, test_user):
        now = datetime.now(UTC)
        end = now + timedelta(days=10)
        cancelling = _sub(db_session, test_user, current_period_end=end,
                          cancel_at_period_end=True)
        assert [n["kind"] for n in billing.due_notices(cancelling, now)] == ["acknowledgment"]
        for row in (
            m.BillingSubscription(user_id=test_user.id, billing_model="annual", tier="growth",
                                  status="active", is_stub=True, current_period_end=end),
            m.BillingSubscription(user_id=test_user.id, billing_model="monthly",
                                  tier="growth", status="active", current_period_end=end),
            m.BillingSubscription(user_id=test_user.id, billing_model="pay_per_meeting",
                                  tier="pay_per_meeting", status="active"),
        ):
            assert billing.due_notices(row, now) == [], row.billing_model

    def test_trial_end_notice_for_annual_and_long_trials_only(self, db_session, test_user):
        now = datetime.now(UTC)
        priced = {"annual": {"price_unit_amount_cents": 349_000, "price_interval": "year"},
                  "monthly": {"price_unit_amount_cents": 34_900, "price_interval": "month"}}
        annual = m.BillingSubscription(
            user_id=test_user.id, billing_model="annual", tier="growth", status="trialing",
            **priced["annual"], trial_started_at=now - timedelta(days=8), trial_ends_at=now + timedelta(days=6))
        assert "trial_end" in {n["kind"] for n in billing.due_notices(annual, now)}
        normal = m.BillingSubscription(
            user_id=test_user.id, billing_model="monthly", tier="growth", status="trialing",
            **priced["monthly"], trial_started_at=now - timedelta(days=8), trial_ends_at=now + timedelta(days=6))
        assert billing.due_notices(normal, now) == [], "a 14-day monthly trial is unchanged"
        long = m.BillingSubscription(
            user_id=test_user.id, billing_model="monthly", tier="growth", status="trialing",
            **priced["monthly"], trial_started_at=now - timedelta(days=30), trial_ends_at=now + timedelta(days=6))
        notices = billing.due_notices(long, now)
        assert [n["kind"] for n in notices] == ["trial_end"]
        assert notices[0]["amount_cents"] == 34_900
        early = m.BillingSubscription(
            user_id=test_user.id, billing_model="annual", tier="growth", status="trialing",
            **priced["annual"], trial_started_at=now, trial_ends_at=now + timedelta(days=8))
        assert "trial_end" not in {n["kind"] for n in billing.due_notices(early, now)}

    def test_a_pilot_extended_trial_gets_a_trial_end_notice(self, client, db_session,
                                                            test_user, mailbox):
        """The checkout's trial (pushed by a pilot) is longer than 31 days, so
        the sweep warns before it ends. With the default 24h grace a pilot
        bought into on day 1 ends 30-31 days later; a 72h grace (admin
        setting, max 168h) makes the trial clearly longer than 31 days."""
        system_settings.set(db_session, pilot_mode.GRACE_SETTING, 72)
        pilot = _active_pilot(db_session, test_user)
        client.post("/billing/checkout", json={"billing_model": "monthly", "tier": "growth", **CONSENT})
        sub = billing.get_subscription(db_session, test_user.id)
        sub.is_stub = False          # as if Stripe had created it
        db_session.commit()
        verdict = pilot_mode.verdict_final_at(pilot, pilot_mode.grace(db_session))
        assert billing.send_renewal_notices(db_session, now=verdict - timedelta(days=8))[
            "sent"] == 0
        assert billing.send_renewal_notices(db_session, now=verdict - timedelta(days=6))[
            "sent"] == 1
        mail = mailbox[-1]
        assert "trial ends" in mail["subject"] and "$349" in mail["subject"]
        assert "every month" in mail["text"]

    def test_a_failed_notice_is_retried_and_capped(self, db_session, test_user, monkeypatch):
        from app.services import email_sender

        now = datetime.now(UTC)
        _sub(db_session, test_user, current_period_end=now + timedelta(days=20))

        def down(**kw):
            raise email_sender.EmailSendError("relay down")

        monkeypatch.setattr(email_sender, "send_email", down)
        for _ in range(5):
            billing.send_renewal_notices(db_session, now=now)
        rows = _notices(db_session)
        assert {r.status for r in rows} == {"failed"}
        assert all(r.attempts == billing.MAX_NOTICE_ATTEMPTS for r in rows)

    def test_a_claimed_notice_is_never_sent_twice(self, db_session, test_user, mailbox):
        now = datetime.now(UTC)
        sub = _sub(db_session, test_user, current_period_end=now + timedelta(days=20))
        (renewal,) = [n for n in billing.due_notices(sub, now) if n["kind"] == "renewal"]
        db_session.add(m.BillingRenewalNotice(
            user_id=test_user.id, subscription_id=sub.id, kind="renewal",
            period_key=renewal["period_key"], status="sending", attempts=1))
        db_session.commit()
        assert billing.send_notice(db_session, sub, renewal, now) == "skipped"
        assert not [msg for msg in mailbox if "renews on" in msg["subject"]]

    def test_the_schema_allows_one_row_per_notice(self, db_session, test_user):
        sub = _sub(db_session, test_user)
        for _ in range(2):
            db_session.add(m.BillingRenewalNotice(user_id=test_user.id, subscription_id=sub.id,
                                                  kind="renewal", period_key="k"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_a_late_notice_is_sent_and_recorded(self, db_session, test_user, caplog):
        now = datetime.now(UTC)
        _sub(db_session, test_user, current_period_end=now + timedelta(days=5, hours=1))
        with caplog.at_level("ERROR"):
            billing.send_renewal_notices(db_session, now=now)
        (row,) = [n for n in _notices(db_session) if n.kind == "renewal"]
        assert row.status == "sent" and row.days_before == 5
        assert "LATE" in caplog.text

    def test_notices_go_only_to_the_subscriptions_own_owner(self, db_session, test_user,
                                                            mailbox):
        other = m.User(email="other-owner@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        now = datetime.now(UTC)
        _sub(db_session, other, current_period_end=now + timedelta(days=20))
        billing.send_renewal_notices(db_session, now=now)
        assert {msg["to"] for msg in mailbox} == {"other-owner@leadpilot.dev"}
        assert _notices(db_session, test_user) == []
        assert {n.user_id for n in _notices(db_session)} == {other.id}


# --------------------------------------------------------------------------
# workers, export, routes
# --------------------------------------------------------------------------


def test_the_notice_sweep_is_scheduled_and_routed():
    from app.workers import billing_tasks  # noqa: F401  (registers the task)
    from app.workers.celery_app import celery_app

    name = "app.workers.billing_tasks.send_renewal_notices"
    assert name in celery_app.tasks
    entries = [e for e in celery_app.conf.beat_schedule.values() if e["task"] == name]
    assert len(entries) == 1
    route = celery_app.conf.task_routes
    assert route.get("app.workers.billing_tasks.*", {}).get("queue") == "default"


def test_notices_are_in_the_account_export():
    from app.services import account_export

    assert account_export.OWNERSHIP["billing_renewal_notices"] == ["user_id"]


def test_billing_routes_stay_personal():
    from app.services import rbac

    assert rbac.is_personal("/billing/checkout") and rbac.is_personal("/billing/cancel")
