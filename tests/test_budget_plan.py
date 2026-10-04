"""F-AI-01b -- the pipeline fits itself to its budget instead of stopping short.

F-AI-01 made the budget a hard cap: a $3 run on the 144-step flow stops around
a quarter of the way through with nothing usable. This is the other half. Given
the budget, the planner decides how many of each phase's nine steps to run:

* step 9 of every phase is the phase SYNTHESIS. The strategy / GTM documents and
  the verification loop are built from those eight rows only (everything reads
  `step_no % 9 == 0`), so they are ALWAYS planned;
* the eight supporting steps are research that feeds the synthesis; the planner
  keeps as many as the budget affords, spread evenly across the phase, and drops
  the rest;
* the plan is stored on the strategy (`steps_per_phase`, NULL = all nine), so a
  resume or a crashed worker follows the same plan.

The hard cap from F-AI-01 stays as the safety net underneath.
Offline: a stub SDK behind the real ClaudeClient, as in test_strategy_budget.
"""

import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.db import models as m
from app.db.models import StrategyStatus
from app.pipeline import budget_plan, engine
from app.verification import loop as vloop
from tests.test_strategy_budget import _step_count, _strategy, metered_client

PRICES = {"anthropic": (3.0, 15.0)}
STEP = budget_plan.estimate_step_micros(PRICES)


class TestPlanner:
    def test_step_estimate_is_priced_from_the_settings(self):
        expected = (settings.pipeline_est_step_input_tokens * 3.0
                    + settings.pipeline_est_step_output_tokens * 15.0)
        assert STEP == int(round(expected))

    def test_a_generous_budget_runs_everything(self):
        assert budget_plan.plan_steps_per_phase(50_000_000, m.FlowType.NO_CLIENTS, PRICES) is None
        assert budget_plan.plan_steps_per_phase(50_000_000, m.FlowType.WITH_CLIENTS, PRICES) is None

    def test_a_small_budget_gets_fewer_steps_per_phase(self):
        k3 = budget_plan.plan_steps_per_phase(3_000_000, m.FlowType.NO_CLIENTS, PRICES)
        k5 = budget_plan.plan_steps_per_phase(5_000_000, m.FlowType.NO_CLIENTS, PRICES)
        assert k3 is not None and 2 <= k3 < 9
        assert k5 is not None and k3 < k5 < 9

    def test_more_budget_never_means_fewer_steps(self):
        last = 0
        for dollars in (2.7, 3, 4, 5, 6, 8, 12, 20):
            k = budget_plan.plan_steps_per_phase(
                int(dollars * 1_000_000), m.FlowType.NO_CLIENTS, PRICES)
            k = 9 if k is None else k
            assert k >= last
            last = k

    @pytest.mark.parametrize("flow", [m.FlowType.NO_CLIENTS, m.FlowType.WITH_CLIENTS])
    @pytest.mark.parametrize("dollars", [3, 4, 5, 6, 8])
    def test_the_plan_is_estimated_to_fit_inside_the_budget(self, flow, dollars):
        budget = dollars * 1_000_000
        k = budget_plan.plan_steps_per_phase(budget, flow, PRICES)
        if k is None:
            return
        pipelines = len(engine.pipelines_for_flow(flow))
        planned_cost = k * 8 * pipelines * STEP
        reserve = int(settings.pipeline_verification_reserve_usd * 1_000_000)
        assert planned_cost + reserve <= budget * settings.pipeline_budget_safety + 1

    def test_a_budget_too_small_for_any_complete_plan_is_refused(self):
        with pytest.raises(budget_plan.BudgetTooSmall) as exc:
            budget_plan.plan_steps_per_phase(500_000, m.FlowType.NO_CLIENTS, PRICES)
        assert exc.value.minimum_micros > 500_000

    def test_the_stated_minimum_is_actually_enough(self):
        for flow in (m.FlowType.NO_CLIENTS, m.FlowType.WITH_CLIENTS):
            minimum = budget_plan.min_budget_micros(flow, PRICES)
            assert budget_plan.plan_steps_per_phase(minimum, flow, PRICES) == 2
            with pytest.raises(budget_plan.BudgetTooSmall):
                budget_plan.plan_steps_per_phase(minimum - 100_000, flow, PRICES)

    @pytest.mark.parametrize("k", range(2, 10))
    def test_every_phase_synthesis_is_always_planned(self, k):
        planned = budget_plan.planned_step_nos(k)
        assert {n for n in range(1, 73) if n % 9 == 0} <= planned
        assert len(planned) == 8 * k

    @pytest.mark.parametrize("k", range(2, 9))
    def test_supporting_steps_are_spread_across_each_phase(self, k):
        planned = budget_plan.planned_step_nos(k)
        for phase in range(8):
            local = sorted(n - phase * 9 for n in planned if phase * 9 < n <= phase * 9 + 9)
            assert local[-1] == 9 and len(local) == k and len(set(local)) == k
        # not just the first few steps of each phase
        if 3 <= k <= 7:
            assert max(n for n in planned if n < 9) > k - 1

    def test_none_means_all_72(self):
        assert budget_plan.planned_step_nos(None) == set(range(1, 73))


class TestEngineFollowsThePlan:
    def test_only_planned_steps_run_and_the_documents_still_assemble(
        self, db_session, product_with_strategy, monkeypatch
    ):
        strategy = _strategy(db_session, product_with_strategy, 50_000_000)
        strategy.steps_per_phase = 3
        db_session.commit()
        stub = metered_client(monkeypatch)

        executed = engine.run_all_steps(db_session, strategy)

        assert executed == 8 * 3 == _step_count(db_session, strategy) == len(stub.calls)
        ran = set(db_session.execute(
            select(m.ResearchStep.step_no).where(m.ResearchStep.strategy_id == strategy.id)
        ).scalars())
        assert ran == budget_plan.planned_step_nos(3)
        engine.assemble_documents(db_session, strategy)
        assert strategy.strategy_document.count("## Phase") == 8

    def test_no_plan_runs_all_72(self, db_session, product_with_strategy, monkeypatch):
        strategy = _strategy(db_session, product_with_strategy, None)
        assert strategy.steps_per_phase is None
        metered_client(monkeypatch)
        assert engine.run_all_steps(db_session, strategy) == 72

    def test_a_planned_run_resumes_on_the_same_plan(
        self, db_session, product_with_strategy, monkeypatch
    ):
        strategy = _strategy(db_session, product_with_strategy, 50_000_000)
        strategy.steps_per_phase = 4
        db_session.commit()
        metered_client(monkeypatch)
        first = engine.run_all_steps(db_session, strategy)
        assert first == 32
        assert engine.run_all_steps(db_session, strategy) == 0  # nothing left, nothing repeated

    def test_the_budget_fitted_run_completes_inside_a_three_dollar_cap(
        self, db_session, product_with_strategy, monkeypatch
    ):
        """The point of the feature, end to end: $3, the no-clients flow, every
        phase reached, no BudgetExceededError. The stub bills a step at the
        planner's own estimate, so this checks the plan against the real gate."""
        from app.services import usage_meter

        budget = 3_000_000
        strategy = _strategy(db_session, product_with_strategy, budget, m.FlowType.NO_CLIENTS)
        strategy.steps_per_phase = budget_plan.plan_steps_per_phase(
            budget, m.FlowType.NO_CLIENTS, PRICES)
        db_session.commit()
        metered_client(
            monkeypatch,
            tokens_in=settings.pipeline_est_step_input_tokens,
            tokens_out=settings.pipeline_est_step_output_tokens,
        )
        # the gate reserves a call's worst case (max_tokens), so give the stub's
        # steps the realistic ceiling the planner assumes
        monkeypatch.setattr(settings, "anthropic_max_tokens", settings.pipeline_est_step_output_tokens)

        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            executed = engine.run_all_steps(db_session, strategy)

        assert executed == 16 * strategy.steps_per_phase
        assert usage_meter.spent_micros(db_session, strategy.id) <= budget


class TestLeanVerification:
    def test_a_planned_strategy_gets_fewer_fix_attempts(self, db_session, product_with_strategy):
        full = _strategy(db_session, product_with_strategy, 5_000_000)
        assert vloop.max_attempts_for(full) == settings.verification_max_retries_per_pass
        full.steps_per_phase = 3
        assert vloop.max_attempts_for(full) == min(settings.verification_max_retries_per_pass, 2)


class TestApi:
    def _post(self, client, product, **body):
        return client.post(f"/products/{product.id}/strategies", json=body)

    def test_three_dollars_on_the_long_flow_is_planned_not_rejected(
        self, client, db_session, product_with_strategy
    ):
        product, _ = product_with_strategy(m.FlowType.NO_CLIENTS)
        resp = self._post(client, product, max_budget_usd=3, flow_type="no_clients")
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert 2 <= body["steps_per_phase"] < 9
        assert body["planned_steps"] == 16 * body["steps_per_phase"]
        row = db_session.get(m.Strategy, uuid.UUID(body["id"]))
        assert row.steps_per_phase == body["steps_per_phase"]

    def test_a_big_budget_keeps_the_full_pipeline(self, client, db_session, product_with_strategy):
        product, _ = product_with_strategy(m.FlowType.NO_CLIENTS)
        body = self._post(client, product, max_budget_usd=50, flow_type="no_clients").json()
        assert body["steps_per_phase"] is None
        assert body["planned_steps"] == 144

    def test_a_budget_below_the_minimum_says_what_the_minimum_is(
        self, client, product_with_strategy
    ):
        product, _ = product_with_strategy(m.FlowType.NO_CLIENTS)
        resp = self._post(client, product, max_budget_usd=1, flow_type="no_clients")
        assert resp.status_code == 422
        assert "at least $" in resp.json()["detail"]

    def test_status_progress_totals_follow_the_plan(
        self, client, db_session, product_with_strategy
    ):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        strategy.steps_per_phase = 3
        db_session.commit()
        body = client.get(f"/strategies/{strategy.id}").json()
        assert body["steps_per_phase"] == 3
        assert body["progress"][0]["total"] == 24
        assert all(p["total"] == 3 for p in body["progress"][0]["phases"])
