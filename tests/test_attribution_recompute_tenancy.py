"""NEW-02 — POST /attribution/recompute must not run a deployment-wide sweep
for an ordinary tenant.

attribution.run_sweep had no tenant parameter, and the endpoint called it for
any authenticated user. So tenant B pressing "Recompute" wrote ledger rows into
tenant A's account and got back counts that included A's outcomes.

After the fix a non-admin's sweep covers only the caller's own outcomes. An
admin's sweep, and the scheduled one (run_sweep with no user_id), stay
deployment-wide.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import attribution
from tests.conftest import auth_headers

NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
URL = "/attribution/recompute"


def _tenant_lead(db_session, user, tag: str) -> m.Lead:
    """A product -> strategy -> lead chain owned by `user`."""
    product = m.Product(user=user, name=f"Product {tag}",
                        description=f"Product of tenant {tag}",
                        type=m.ProductType.SKILL)
    db_session.add(product)
    db_session.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.WITH_CLIENTS)
    db_session.add(strategy)
    db_session.flush()
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=f"NEW02-{tag}",
                  full_name=f"Lead {tag}", company=f"Company {tag}",
                  email=f"lead-{tag.lower()}@tenant.test",
                  status=m.LeadStatus.CONTACTED)
    db_session.add(lead)
    db_session.commit()
    return lead


def _booked(db_session, lead: m.Lead) -> m.Outcome:
    """An uncredited outcome: exactly what the sweep looks for."""
    outcome = m.Outcome(lead_id=lead.id, strategy_id=lead.strategy_id,
                        event=m.OutcomeEvent.BOOKED, channel="email", ts=NOW)
    db_session.add(outcome)
    db_session.commit()
    return outcome


def _entries_for(db_session, lead: m.Lead) -> list:
    return db_session.execute(select(m.AttributionEntry).where(
        m.AttributionEntry.lead_id == lead.id)).scalars().all()


@pytest.fixture()
def lead_a(db_session, test_user):
    """Tenant A is the canonical test_user."""
    return _tenant_lead(db_session, test_user, "A")


@pytest.fixture()
def tenant_b(db_session):
    user = m.User(email="tenant-b-attr@test.dev", email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def lead_b(db_session, tenant_b):
    return _tenant_lead(db_session, tenant_b, "B")


@pytest.fixture()
def admin(db_session):
    user = m.User(email="admin-attr@test.dev", email_verified=True, is_admin=True)
    db_session.add(user)
    db_session.commit()
    return user


class TestNonAdminSweepIsScopedToTheCaller:
    def test_it_does_not_write_another_tenants_ledger(self, client, db_session,
                                                      lead_a, tenant_b):
        _booked(db_session, lead_a)
        response = client.post(URL, headers=auth_headers(tenant_b))
        assert response.status_code == 200, response.text
        assert _entries_for(db_session, lead_a) == []

    def test_it_does_not_report_another_tenants_volume(self, client, db_session,
                                                       lead_a, tenant_b):
        _booked(db_session, lead_a)
        counts = client.post(URL, headers=auth_headers(tenant_b)).json()
        assert counts == {"checked": 0, "recorded": 0, "skipped": 0, "failed": 0}

    def test_it_still_credits_the_callers_own_outcomes(self, client, db_session,
                                                       lead_a, lead_b, tenant_b):
        _booked(db_session, lead_a)
        _booked(db_session, lead_b)
        counts = client.post(URL, headers=auth_headers(tenant_b)).json()
        assert counts["checked"] == 1
        assert counts["recorded"] == 1
        own = _entries_for(db_session, lead_b)
        assert len(own) == 1
        assert own[0].user_id == tenant_b.id
        assert _entries_for(db_session, lead_a) == []


class TestDeploymentWideSweepIsUnchanged:
    def test_an_admin_still_sweeps_every_tenant(self, client, db_session, lead_a,
                                                lead_b, admin):
        _booked(db_session, lead_a)
        _booked(db_session, lead_b)
        counts = client.post(URL, headers=auth_headers(admin)).json()
        assert counts["recorded"] == 2
        assert len(_entries_for(db_session, lead_a)) == 1
        assert len(_entries_for(db_session, lead_b)) == 1

    def test_the_scheduled_sweep_still_covers_every_tenant(self, db_session, lead_a,
                                                           lead_b):
        """analytics_tasks.run_attribution_sweep calls run_sweep(session)."""
        _booked(db_session, lead_a)
        _booked(db_session, lead_b)
        counts = attribution.run_sweep(db_session, now=NOW)
        assert counts["recorded"] == 2
        assert len(_entries_for(db_session, lead_a)) == 1
        assert len(_entries_for(db_session, lead_b)) == 1
