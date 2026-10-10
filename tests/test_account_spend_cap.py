"""P0-5 -- every ACCOUNT has a daily AI spend cap, enforced before each call.

BEFORE: each strategy run had a dollar budget (F-AI-01), but nothing capped an
account. Plans scale/pro/enterprise allowed unlimited strategies at up to $50
each, and the audit's numbers -- ~$8.29 per Flow-2 strategy, 2 strategies an
hour -- put one FREE account at ~$398/day of Anthropic spend.

NOW: plans.PLANS[...]["max_ai_spend_usd_per_day"] is a finite cap for every
plan. Inside pipeline, verification and lead-scoring scopes, usage_meter
refuses a model call whose worst case would take the account past what it has
already spent since 00:00 UTC. The API refuses to create or resume a strategy
once the day's cap is used up (429). Spend from every purpose counts toward the
day; sends, meeting briefs and call analysis are counted but not stopped
mid-flight.

Offline: SQLite, a stub SDK behind the REAL ClaudeClient (helpers shared with
tests/test_strategy_budget.py), so the real gate is under test.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core import plans
from app.db import models as m
from app.db.models import StrategyStatus
from app.services import usage_meter
from app.services.anthropic_client import is_permanent_error
from app.workers.tasks import run_pipeline, run_verification
from tests.test_strategy_budget import _NoCloseSession, _strategy, metered_client

FREE_CAP = 10_000_000  # $10.00 in micros (plans.py, "free")


def _spend(db, user_id, micros, *, purpose="pipeline", ts=None):
    row = m.ApiUsage(user_id=user_id, strategy_id=None, provider="anthropic",
                     model="x", purpose=purpose, calls=1, input_tokens=0,
                     output_tokens=0, cost_micros=micros)
    if ts is not None:
        row.ts = ts
    db.add(row)
    db.commit()


class TestPlans:
    def test_every_plan_has_a_finite_positive_daily_cap(self):
        for name, plan in plans.PLANS.items():
            cap = plan.get("max_ai_spend_usd_per_day")
            assert isinstance(cap, (int, float)) and cap > 0, name

    def test_cap_follows_the_accounts_plan(self, db_session, test_user):
        assert usage_meter.account_daily_cap(db_session, test_user.id) == (FREE_CAP, "free")
        test_user.plan = m.PlanTier.SCALE
        db_session.commit()
        cap, plan = usage_meter.account_daily_cap(db_session, test_user.id)
        assert plan == "scale" and cap == int(plans.PLANS["scale"]["max_ai_spend_usd_per_day"] * 1_000_000)

    def test_unknown_account_has_no_cap(self, db_session):
        assert usage_meter.account_daily_cap(db_session, uuid.uuid4()) == (None, "")
        assert usage_meter.account_daily_cap(db_session, None) == (None, "")


class TestGate:
    def test_call_that_fits_under_todays_cap_is_allowed(self, db_session, product_with_strategy, test_user):
        strategy = _strategy(db_session, product_with_strategy, None)
        _spend(db_session, test_user.id, FREE_CAP - 500_000)  # $0.50 left
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            # 3,000 chars ~ 1,000 tokens in ($0.003) + 4,096 out ($0.06): fits
            usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)

    def test_call_that_could_cross_todays_cap_is_refused(self, db_session, product_with_strategy, test_user):
        strategy = _strategy(db_session, product_with_strategy, None)
        _spend(db_session, test_user.id, FREE_CAP - 50_000)  # $0.05 left
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            with pytest.raises(usage_meter.AccountBudgetExceededError) as exc:
                usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)
        message = str(exc.value)
        assert "daily AI limit" in message and "free" in message and "00:00 UTC" in message
        assert exc.value.budget_micros == FREE_CAP

    def test_spend_inside_the_scope_counts(self, db_session, product_with_strategy):
        strategy = _strategy(db_session, product_with_strategy, None)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            usage_meter.note("anthropic", "x", 0, 660_000)  # 660k * $15/Mtok = $9.90
            with pytest.raises(usage_meter.AccountBudgetExceededError):
                usage_meter.check_budget(input_chars=300, max_output_tokens=10_000)

    def test_yesterdays_spend_does_not_count(self, db_session, product_with_strategy, test_user):
        strategy = _strategy(db_session, product_with_strategy, None)
        yesterday = usage_meter.utc_day_start() - timedelta(seconds=1)
        _spend(db_session, test_user.id, FREE_CAP * 5, ts=yesterday)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)  # no raise

    def test_spend_from_every_purpose_counts(self, db_session, product_with_strategy, test_user):
        strategy = _strategy(db_session, product_with_strategy, None)
        _spend(db_session, test_user.id, FREE_CAP, purpose="outreach")
        with usage_meter.owner_scope(db_session, strategy, "verification"):
            with pytest.raises(usage_meter.AccountBudgetExceededError):
                usage_meter.check_budget(input_chars=10, max_output_tokens=10)

    def test_another_accounts_spend_does_not_count(self, db_session, product_with_strategy):
        other = m.User(email=f"other-{uuid.uuid4().hex[:6]}@example.com",
                       password_hash="x", email_verified=True)
        db_session.add(other)
        db_session.commit()
        _spend(db_session, other.id, FREE_CAP * 3)
        strategy = _strategy(db_session, product_with_strategy, None)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)  # no raise

    @pytest.mark.parametrize("purpose", ["outreach", "meeting_prep", "call_analysis"])
    def test_sends_briefs_and_calls_are_counted_but_not_stopped(
            self, db_session, product_with_strategy, test_user, purpose):
        _spend(db_session, test_user.id, FREE_CAP * 2)
        with usage_meter.scope(db_session, user_id=test_user.id, purpose=purpose):
            usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)  # no raise

    def test_lead_scoring_is_stopped(self, db_session, test_user):
        _spend(db_session, test_user.id, FREE_CAP)
        with usage_meter.scope(db_session, user_id=test_user.id, purpose="lead_scoring"):
            with pytest.raises(usage_meter.AccountBudgetExceededError):
                usage_meter.check_budget(input_chars=10, max_output_tokens=10)

    def test_the_stricter_of_strategy_budget_and_account_cap_wins(
            self, db_session, product_with_strategy, test_user):
        strategy = _strategy(db_session, product_with_strategy, 50_000)  # $0.05 strategy budget
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            with pytest.raises(usage_meter.BudgetExceededError) as exc:
                usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)
        assert not isinstance(exc.value, usage_meter.AccountBudgetExceededError)

    def test_account_cap_error_is_permanent_never_retried(self):
        assert is_permanent_error(usage_meter.AccountBudgetExceededError(
            "x", budget_micros=1, spent_micros=1))


@pytest.fixture
def task_session(monkeypatch, db_session):
    monkeypatch.setattr("app.workers.tasks.SessionLocal", lambda: _NoCloseSession(db_session))
    return db_session


class TestTasks:
    def test_pipeline_stops_cleanly_on_the_account_cap(
            self, task_session, product_with_strategy, test_user, monkeypatch):
        strategy = _strategy(task_session, product_with_strategy, None)  # no strategy budget
        _spend(task_session, test_user.id, FREE_CAP - 100_000)  # $0.10 left today
        metered_client(monkeypatch)
        verify_started = []
        monkeypatch.setattr(run_verification, "delay", lambda *a, **k: verify_started.append(a))

        result = run_pipeline.apply(args=[str(strategy.id)], retries=0, throw=False)

        assert result.state == "SUCCESS", "a cap stop is an outcome, not a crash to retry"
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.BUDGET_EXHAUSTED
        assert "daily AI limit" in (strategy.error or "")
        assert verify_started == []
        spent = usage_meter.account_spent_today_micros(task_session, test_user.id)
        assert spent <= FREE_CAP, "the gate must never let the account run past its cap"


class TestApi:
    def test_create_is_refused_once_the_day_is_used_up(
            self, client, db_session, product_with_strategy, test_user, enqueued):
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS)
        _spend(db_session, test_user.id, FREE_CAP)
        before = len(enqueued)
        resp = client.post(f"/products/{product.id}/strategies", json={})
        assert resp.status_code == 429, resp.text
        detail = resp.json()["detail"]
        assert detail["error"] == "daily_ai_limit_reached"
        assert detail["limit_usd"] == 10.0 and detail["plan"] == "free"
        assert len(enqueued) == before

    def test_create_is_allowed_below_the_cap(self, client, db_session, product_with_strategy, test_user):
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS)
        _spend(db_session, test_user.id, FREE_CAP - 1_000_000)
        resp = client.post(f"/products/{product.id}/strategies", json={})
        assert resp.status_code == 202, resp.text

    def test_resume_is_refused_once_the_day_is_used_up(
            self, client, db_session, product_with_strategy, test_user, enqueued):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        strategy.status = StrategyStatus.BUDGET_EXHAUSTED
        strategy.error = "daily AI limit reached"
        db_session.commit()
        _spend(db_session, test_user.id, FREE_CAP)
        before = len(enqueued)
        resp = client.post(f"/strategies/{strategy.id}/resume")
        assert resp.status_code == 429, resp.text
        db_session.refresh(strategy)
        assert strategy.status is StrategyStatus.BUDGET_EXHAUSTED
        assert len(enqueued) == before
