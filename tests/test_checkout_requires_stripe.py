"""P0-2 (audit RF-2) — no free plans in production when Stripe is not configured.

With STRIPE_SECRET_KEY empty the app runs in stub mode: start_checkout()
activates the chosen plan locally, no payment taken. That is intended for
development and test (tests/test_billing.py::TestStubCheckout), but in
production it meant any signed-in user could take any tier -- Enterprise
included -- for free.

What must hold:
  * production + no key -> POST /billing/checkout is 503 and NOTHING changes:
    users.plan stays FREE and no billing_subscriptions row is written;
  * a whitespace-only key counts as no key;
  * production + a key -> the normal Stripe Checkout path runs;
  * outside production, stub mode is unchanged.
"""

import pytest
from sqlalchemy import select

from app.config import settings
from app.db import models as m
from app.integrations import stripe_billing

MONTHLY_ENTERPRISE = {"billing_model": "monthly", "tier": "enterprise"}


@pytest.fixture()
def production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")


def _subscriptions(db_session, user):
    db_session.expire_all()
    return db_session.execute(
        select(m.BillingSubscription).where(m.BillingSubscription.user_id == user.id)
    ).scalars().all()


def _assert_nothing_granted(db_session, user):
    db_session.refresh(user)
    assert user.plan is m.PlanTier.FREE
    assert _subscriptions(db_session, user) == []


class TestProductionWithoutStripe:
    @pytest.mark.parametrize("key", ["", "   "], ids=["empty", "whitespace"])
    def test_checkout_is_refused_and_the_plan_is_untouched(
            self, client, db_session, test_user, production, monkeypatch, key):
        monkeypatch.setattr(settings, "stripe_secret_key", key)
        resp = client.post("/billing/checkout", json=MONTHLY_ENTERPRISE)
        assert resp.status_code == 503, resp.text
        assert "payments are not configured" in resp.json()["detail"].lower()
        _assert_nothing_granted(db_session, test_user)

    def test_pay_per_meeting_is_refused_too(self, client, db_session, test_user, production,
                                            monkeypatch):
        monkeypatch.setattr(settings, "stripe_secret_key", "")
        resp = client.post("/billing/checkout", json={"billing_model": "pay_per_meeting"})
        assert resp.status_code == 503, resp.text
        _assert_nothing_granted(db_session, test_user)


class TestProductionWithStripe:
    def test_checkout_goes_to_stripe_and_grants_nothing_yet(
            self, client, db_session, test_user, production, monkeypatch):
        monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_123")
        monkeypatch.setattr(stripe_billing, "create_customer",
                            lambda **kw: {"id": "cus_123"})
        monkeypatch.setattr(stripe_billing, "create_subscription_checkout",
                            lambda **kw: {"id": "cs_sub",
                                          "url": "https://checkout.stripe.com/c/pay/cs_sub"})
        resp = client.post("/billing/checkout", json=MONTHLY_ENTERPRISE)
        assert resp.status_code == 200, resp.text
        assert resp.json()["mode"] == "stripe"
        assert resp.json()["checkout_url"].startswith("https://checkout.stripe.com/")
        db_session.refresh(test_user)
        assert test_user.plan is m.PlanTier.FREE, "nothing is granted before payment"
        (sub,) = _subscriptions(db_session, test_user)
        assert sub.status == "incomplete" and sub.is_stub is False


class TestStubModeOutsideProduction:
    def test_development_stub_checkout_still_activates_locally(
            self, client, db_session, test_user, monkeypatch):
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "stripe_secret_key", "")
        resp = client.post("/billing/checkout", json=MONTHLY_ENTERPRISE)
        assert resp.status_code == 200, resp.text
        assert resp.json()["mode"] == "stub"
