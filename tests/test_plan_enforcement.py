"""Plan enforcement -- the advertised per-plan limits are now enforced.

BEFORE: max_leads_per_strategy, max_sequence_steps and channels were declared
in app/core/plans.py and checked nowhere (BASELINE.md "Plan enforcement",
HIGH). A Free account could build 20-step LinkedIn + WhatsApp + phone
sequences on unlimited leads.

NOW, each answered with the existing 402 plan_limit_exceeded body:
  * steps     -- POST /strategies/{id}/sequences, and again at every launch
                 (enroll / approve), so a downgrade cannot be launched around.
  * channels  -- the same three points, for every channel a step sends on;
                 POST /leads/{id}/call needs "phone".
  * leads     -- POST /strategies/{id}/leads/source refuses a full strategy
                 and asks for no more than the room left; the sourcing worker
                 stops adding at the limit (two batches, or a downgrade, cannot
                 overshoot). DROPPED leads (suppressed, erased) do not count.

Offline; the real API and the real worker with FakeLeadSource.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.core import plans
from app.db import models as m
from app.services import system_settings
from app.workers.lead_tasks import source_leads_impl, strategy_lead_count
from tests.conftest import FakeLeadSource, make_raw


def _plan(db, user, tier):
    user.plan = tier
    db.commit()


def _steps(n, **extra):
    return [{"step_no": i, "template": f"step {i}", **extra} for i in range(1, n + 1)]


def _assert_402(resp, limit):
    assert resp.status_code == 402, resp.text
    detail = resp.json()["detail"]
    assert detail["error"] == "plan_limit_exceeded"
    assert detail["limit"] == limit
    assert detail["message"]
    return detail


def _seed(db, strategy, n, status=m.LeadStatus.VERIFIED, prefix="s"):
    for i in range(n):
        db.add(m.Lead(strategy_id=strategy.id, source="seed", external_id=f"{prefix}{i}",
                      full_name=f"P {i}", email=f"{prefix}{i}@x{i}.example", status=status))
    db.commit()


# --------------------------------------------------------------------------
# Helpers in app/core/plans.py
# --------------------------------------------------------------------------

class TestHelpers:
    def test_every_send_channel_maps_to_a_plan_channel(self):
        known = {c for p in plans.PLANS.values() for c in p["channels"]}
        for channel in m.ChannelType:
            assert plans.PLAN_CHANNEL_NAME[channel.value] in known, channel

    def test_quantity_check(self):
        free = m.User(email="q@x.example", plan=m.PlanTier.FREE)
        plans.check_plan_quantity(free, "max_sequence_steps", 5, "ok")
        with pytest.raises(plans.PlanLimitExceeded) as exc:
            plans.check_plan_quantity(free, "max_sequence_steps", 6, "This has 6 steps.")
        assert "Free plan allows 5 sequence steps. This has 6 steps." == exc.value.message
        assert exc.value.upgrade_to == "starter"
        scale = m.User(email="s@x.example", plan=m.PlanTier.SCALE)
        plans.check_plan_quantity(scale, "max_sequence_steps", 10_000, "unlimited")

    def test_remaining(self):
        free = m.User(email="r@x.example", plan=m.PlanTier.FREE)
        assert plans.plan_limit_remaining(free, "max_leads_per_strategy", 40) == 60
        assert plans.plan_limit_remaining(free, "max_leads_per_strategy", 500) == 0
        ent = m.User(email="e@x.example", plan=m.PlanTier.ENTERPRISE)
        assert plans.plan_limit_remaining(ent, "max_leads_per_strategy", 10**9) is None

    def test_email_is_the_gmail_channel(self):
        free = m.User(email="g@x.example", plan=m.PlanTier.FREE)
        plans.check_send_channel(free, m.ChannelType.EMAIL)
        with pytest.raises(plans.PlanLimitExceeded):
            plans.check_send_channel(free, m.ChannelType.LINKEDIN)

    def test_legacy_pro_keeps_every_channel(self):
        assert set(plans.PLANS["pro"]["channels"]) == set(plans.PLAN_CHANNEL_NAME.values())


# --------------------------------------------------------------------------
# Sequences
# --------------------------------------------------------------------------

class TestSequenceCreate:
    def test_free_allows_five_steps(self, client, verified_strategy):
        resp = client.post(f"/strategies/{verified_strategy.id}/sequences",
                           json={"name": "ok", "channel": "email", "steps": _steps(5)})
        assert resp.status_code == 201, resp.text

    def test_free_refuses_six_steps(self, client, db_session, verified_strategy):
        before = db_session.execute(select(func.count(m.Sequence.id))).scalar_one()
        resp = client.post(f"/strategies/{verified_strategy.id}/sequences",
                           json={"name": "long", "channel": "email", "steps": _steps(6)})
        detail = _assert_402(resp, "max_sequence_steps")
        assert detail["current_plan"] == "free" and detail["upgrade_to"] == "starter"
        assert "6 steps" in detail["message"]
        assert db_session.execute(select(func.count(m.Sequence.id))).scalar_one() == before

    def test_starter_allows_ten_steps(self, client, db_session, test_user, verified_strategy):
        _plan(db_session, test_user, m.PlanTier.STARTER)
        resp = client.post(f"/strategies/{verified_strategy.id}/sequences",
                           json={"name": "ten", "channel": "email", "steps": _steps(10)})
        assert resp.status_code == 201, resp.text

    def test_free_refuses_a_linkedin_sequence(self, client, verified_strategy):
        resp = client.post(f"/strategies/{verified_strategy.id}/sequences",
                           json={"name": "li", "channel": "linkedin", "steps": _steps(1)})
        detail = _assert_402(resp, "channels")
        assert "linkedin" in detail["message"]

    def test_a_single_step_override_is_checked_too(self, client, verified_strategy):
        steps = _steps(2)
        steps[1]["channel"] = "linkedin"
        resp = client.post(f"/strategies/{verified_strategy.id}/sequences",
                           json={"name": "mixed", "channel": "email", "steps": steps})
        _assert_402(resp, "channels")

    def test_growth_allows_linkedin(self, client, db_session, test_user, verified_strategy):
        _plan(db_session, test_user, m.PlanTier.GROWTH)
        resp = client.post(f"/strategies/{verified_strategy.id}/sequences",
                           json={"name": "li", "channel": "linkedin", "steps": _steps(1)})
        assert resp.status_code == 201, resp.text

    def test_shape_errors_come_before_the_plan(self, client, verified_strategy):
        # gapped steps on a plan-violating sequence: 422 first
        resp = client.post(f"/strategies/{verified_strategy.id}/sequences", json={
            "name": "bad", "channel": "linkedin",
            "steps": [{"step_no": 1, "template": "a"}, {"step_no": 3, "template": "b"}]})
        assert resp.status_code == 422


class TestLaunchAfterDowngrade:
    @pytest.fixture()
    def linkedin_sequence(self, client, db_session, test_user, verified_strategy):
        _plan(db_session, test_user, m.PlanTier.GROWTH)
        resp = client.post(f"/strategies/{verified_strategy.id}/sequences",
                           json={"name": "li", "channel": "linkedin", "steps": _steps(1)})
        assert resp.status_code == 201, resp.text
        _plan(db_session, test_user, m.PlanTier.FREE)
        return resp.json()["id"]

    def test_enroll_is_refused(self, client, db_session, linkedin_sequence):
        resp = client.post(f"/sequences/{linkedin_sequence}/enroll", json={})
        _assert_402(resp, "channels")
        assert db_session.execute(select(func.count(m.SequenceEnrollment.id))).scalar_one() == 0

    def test_approve_is_refused(self, client, db_session, linkedin_sequence):
        import uuid  # noqa: PLC0415
        seq = db_session.get(m.Sequence, uuid.UUID(linkedin_sequence))
        seq.status = m.SequenceStatus.PENDING_APPROVAL  # an SDR asked before the downgrade
        db_session.commit()
        resp = client.post(f"/sequences/{linkedin_sequence}/approve", json={})
        _assert_402(resp, "channels")
        db_session.refresh(seq)
        assert seq.status is m.SequenceStatus.PENDING_APPROVAL


# --------------------------------------------------------------------------
# Leads
# --------------------------------------------------------------------------

class TestLeadSourcingApi:
    def test_full_strategy_is_refused(self, leads_client, db_session, verified_strategy,
                                      chain_calls):
        _seed(db_session, verified_strategy, 100)
        resp = leads_client.post(f"/strategies/{verified_strategy.id}/leads/source", json={})
        detail = _assert_402(resp, "max_leads_per_strategy")
        assert "100" in detail["message"]
        assert chain_calls == []

    def test_request_is_cut_to_the_room_left(self, leads_client, db_session, verified_strategy):
        _seed(db_session, verified_strategy, 95)
        resp = leads_client.post(f"/strategies/{verified_strategy.id}/leads/source",
                                 json={"max_leads": 50})
        assert resp.status_code == 202, resp.text
        assert resp.json()["requested_leads"] == 5

    def test_dropped_leads_do_not_count(self, leads_client, db_session, verified_strategy):
        _seed(db_session, verified_strategy, 100, status=m.LeadStatus.DROPPED)
        resp = leads_client.post(f"/strategies/{verified_strategy.id}/leads/source",
                                 json={"max_leads": 50})
        assert resp.status_code == 202, resp.text
        assert resp.json()["requested_leads"] == 50

    def test_unlimited_plan_is_not_cut(self, leads_client, db_session, test_user,
                                       verified_strategy):
        _plan(db_session, test_user, m.PlanTier.ENTERPRISE)
        _seed(db_session, verified_strategy, 150)
        resp = leads_client.post(f"/strategies/{verified_strategy.id}/leads/source",
                                 json={"max_leads": 50})
        assert resp.status_code == 202, resp.text
        assert resp.json()["requested_leads"] == 50


class TestLeadSourcingWorker:
    def test_worker_stops_at_the_limit(self, db_session, verified_strategy):
        _seed(db_session, verified_strategy, 98)
        batch = m.LeadBatch(strategy_id=verified_strategy.id, requested_leads=50,
                            source_provider="fakesource", verifier_provider="fakeverifier")
        db_session.add(batch)
        db_session.commit()
        source = FakeLeadSource(feed=[make_raw(i, email=f"n{i}@new{i}.example") for i in range(5)])
        counts = source_leads_impl(db_session, batch.id, source=source)
        assert counts == {"added": 2, "duplicates": 0, "suppressed": 0, "plan_limit": 3}
        assert strategy_lead_count(db_session, verified_strategy.id) == 100

    def test_downgrade_between_request_and_worker(self, db_session, test_user,
                                                  verified_strategy):
        _seed(db_session, verified_strategy, 100)
        batch = m.LeadBatch(strategy_id=verified_strategy.id, requested_leads=50,
                            source_provider="fakesource", verifier_provider="fakeverifier")
        db_session.add(batch)
        db_session.commit()  # requested on a bigger plan; the account is Free now
        source = FakeLeadSource(feed=[make_raw(i, email=f"d{i}@d{i}.example") for i in range(3)])
        counts = source_leads_impl(db_session, batch.id, source=source)
        assert counts["added"] == 0 and counts["plan_limit"] == 3


# --------------------------------------------------------------------------
# Calls
# --------------------------------------------------------------------------

class TestCalls:
    def test_free_cannot_place_an_ai_call(self, client, db_session, verified_strategy):
        system_settings.set(db_session, "phone_calling_enabled", True)
        db_session.commit()
        _seed(db_session, verified_strategy, 1, prefix="call")
        lead = db_session.execute(select(m.Lead).where(
            m.Lead.strategy_id == verified_strategy.id)).scalars().first()
        lead.phone = "+14155550100"
        db_session.commit()
        resp = client.post(f"/leads/{lead.id}/call", json={})
        detail = _assert_402(resp, "channels")
        assert "phone" in detail["message"]
        assert db_session.execute(select(func.count(m.Call.id))).scalar_one() == 0
