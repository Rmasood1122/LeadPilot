"""F-AI-01 -- a strategy run has a dollar budget, and it is enforced.

BEFORE: nothing in the application limited what a pipeline run could spend.
usage_meter priced model calls AFTER the fact and only when its scope closed,
`strategies` had no budget column, and the only brake was the balance on the
Anthropic account. A full no-clients run (144 steps + a 10-pass verification
loop) is the most expensive operation in the product.

NOW: `strategies.budget_micros` is the cap. Before every Claude call the
gateway asks usage_meter whether the call could take the run past the cap, and
refuses it if so. The run ends in StrategyStatus.BUDGET_EXHAUSTED -- resumable,
nothing already paid for is thrown away.

Everything here runs offline. The model is a stub SDK object behind the REAL
ClaudeClient, so the real gate (anthropic_client.complete -> usage_meter) is
what is under test, not a fake that would pass either way.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.db import models as m
from app.db.models import StrategyStatus
from app.pipeline import engine
from app.services import usage_meter
from app.services.anthropic_client import ClaudeClient, is_permanent_error
from app.workers.tasks import run_pipeline, run_verification

# claude price defaults are 3.0 in / 15.0 out USD per Mtok == micros per token
PER_CALL_MICROS = 1000 * 3 + 1000 * 15  # 1000 tokens in, 1000 out = 18,000


class _Block:
    type = "text"
    text = "ok"


class _Usage:
    def __init__(self, tokens_in, tokens_out):
        self.input_tokens = tokens_in
        self.output_tokens = tokens_out


class _Resp:
    def __init__(self, tokens_in, tokens_out):
        self.content = [_Block()]
        self.stop_reason = "end_turn"
        self.usage = _Usage(tokens_in, tokens_out)


class _StubSDK:
    """Stands in for anthropic.Anthropic. `on_call(n)` lets a test look at the
    world at the moment the n-th request is made."""

    def __init__(self, tokens_in=1000, tokens_out=1000, on_call=None):
        self.calls = []
        self._in, self._out, self._on_call = tokens_in, tokens_out, on_call
        self.messages = self

    def create(self, **request):
        self.calls.append(request)
        if self._on_call:
            self._on_call(len(self.calls))
        return _Resp(self._in, self._out)


def metered_client(monkeypatch, **kw) -> _StubSDK:
    """The REAL ClaudeClient (so complete() and its budget gate run) over a stub."""
    stub = _StubSDK(**kw)
    client = ClaudeClient.__new__(ClaudeClient)
    client._client = stub
    for target in ("app.pipeline.engine.get_client", "app.verification.loop.get_client"):
        monkeypatch.setattr(target, lambda: client)
    return stub


def _step_count(db, strategy):
    return db.execute(
        select(func.count(m.ResearchStep.id)).where(m.ResearchStep.strategy_id == strategy.id)
    ).scalar_one()


def _strategy(db, product_with_strategy, budget_micros, flow=m.FlowType.WITH_CLIENTS):
    _, strategy = product_with_strategy(flow)
    strategy.budget_micros = budget_micros
    strategy.status = StrategyStatus.RESEARCHING
    db.commit()
    return strategy


# ---------------------------------------------------------------------------
# The meter: pricing, the gate, durability
# ---------------------------------------------------------------------------
class TestMeterAndGate:
    def test_schema_has_a_nullable_budget_column(self):
        col = m.Strategy.__table__.c.budget_micros
        assert col.nullable is True
        assert str(col.type) == "BIGINT"
        assert StrategyStatus.BUDGET_EXHAUSTED.value == "budget_exhausted"

    def test_spend_is_priced_from_the_admin_settings(self, db_session, product_with_strategy):
        strategy = _strategy(db_session, product_with_strategy, 10_000_000)
        with usage_meter.owner_scope(db_session, strategy, "pipeline") as scope:
            usage_meter.note("anthropic", "claude-sonnet-4-6", 1_000_000, 0)
            usage_meter.note("anthropic", "claude-sonnet-4-6", 0, 1_000_000)
            assert scope.spent_micros == 3_000_000 + 15_000_000

    def test_no_budget_means_no_gate(self, db_session, product_with_strategy):
        strategy = _strategy(db_session, product_with_strategy, None)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            usage_meter.note("anthropic", "x", 500_000_000, 500_000_000)
            usage_meter.check_budget(input_chars=10**9, max_output_tokens=10**6)  # no raise

    def test_a_call_that_could_cross_the_cap_is_refused(self, db_session, product_with_strategy):
        # $0.05 cap; a 4096-token reply alone can cost 4096*15 = $0.0614.
        strategy = _strategy(db_session, product_with_strategy, 50_000)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            with pytest.raises(usage_meter.BudgetExceededError) as exc:
                usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)
        assert exc.value.budget_micros == 50_000
        assert "budget" in str(exc.value).lower()

    def test_a_call_that_fits_is_allowed(self, db_session, product_with_strategy):
        strategy = _strategy(db_session, product_with_strategy, 5_000_000)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            usage_meter.check_budget(input_chars=3000, max_output_tokens=4096)  # no raise

    def test_prior_spend_counts_against_a_new_scope(self, db_session, product_with_strategy):
        strategy = _strategy(db_session, product_with_strategy, 1_000_000)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            usage_meter.note("anthropic", "x", 0, 65_000)  # 975,000 micros
        assert usage_meter.spent_micros(db_session, strategy.id) == 975_000
        with usage_meter.owner_scope(db_session, strategy, "verification"):
            with pytest.raises(usage_meter.BudgetExceededError):
                usage_meter.check_budget(input_chars=100, max_output_tokens=4096)

    def test_spend_is_scoped_to_pipeline_and_verification_only(
        self, db_session, product_with_strategy
    ):
        # The budget is for RUNNING THE PIPELINE. Outreach copy written later
        # for the same strategy is a different cost and must not eat it.
        strategy = _strategy(db_session, product_with_strategy, 1_000_000)
        with usage_meter.owner_scope(db_session, strategy, "send"):
            usage_meter.note("anthropic", "x", 0, 60_000)
        assert usage_meter.spent_micros(db_session, strategy.id) == 0

    def test_budget_exceeded_is_permanent_never_retried(self):
        err = usage_meter.BudgetExceededError("x", budget_micros=1, spent_micros=1)
        assert is_permanent_error(err) is True

    def test_flush_active_makes_spend_durable_mid_scope(self, db_session, product_with_strategy):
        strategy = _strategy(db_session, product_with_strategy, 5_000_000)
        with usage_meter.owner_scope(db_session, strategy, "pipeline") as scope:
            usage_meter.note("anthropic", "x", 1000, 1000)
            usage_meter.flush_active(db_session)
            # visible to a reader BEFORE the scope closes (a SIGKILLed worker
            # never reaches the close), and not counted twice afterwards
            assert usage_meter.spent_micros(db_session, strategy.id) == PER_CALL_MICROS
            usage_meter.note("anthropic", "x", 1000, 1000)
            assert scope.spent_micros == 2 * PER_CALL_MICROS
        assert usage_meter.spent_micros(db_session, strategy.id) == 2 * PER_CALL_MICROS


# ---------------------------------------------------------------------------
# The engine: stops before the cap, spends exactly what it recorded, resumes
# ---------------------------------------------------------------------------
class TestEngineEnforcement:
    def test_pipeline_stops_before_the_cap_is_crossed(
        self, db_session, product_with_strategy, monkeypatch
    ):
        strategy = _strategy(db_session, product_with_strategy, 1_000_000)  # $1.00
        stub = metered_client(monkeypatch)

        with pytest.raises(usage_meter.BudgetExceededError):
            with usage_meter.owner_scope(db_session, strategy, "pipeline"):
                engine.run_all_steps(db_session, strategy)

        done = _step_count(db_session, strategy)
        assert 0 < done < 72, "it must have started, and must not have finished"
        assert len(stub.calls) == done, "a refused call never reaches the API"
        spent = usage_meter.spent_micros(db_session, strategy.id)
        assert spent == done * PER_CALL_MICROS
        assert spent <= 1_000_000, "the cap is a ceiling, not a target to overshoot"

    def test_spend_is_flushed_after_each_step(self, db_session, product_with_strategy, monkeypatch):
        strategy = _strategy(db_session, product_with_strategy, 50_000_000)
        seen = {}

        def look(n):
            if n == 5:
                seen["spent"] = usage_meter.spent_micros(db_session, strategy.id)

        metered_client(monkeypatch, on_call=look)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            engine.run_all_steps(db_session, strategy)
        assert seen["spent"] == 4 * PER_CALL_MICROS, (
            "a worker killed mid-run must not lose the spend of completed steps"
        )

    def test_raising_the_budget_resumes_without_double_counting(
        self, db_session, product_with_strategy, monkeypatch
    ):
        strategy = _strategy(db_session, product_with_strategy, 1_000_000)
        stub = metered_client(monkeypatch)
        with pytest.raises(usage_meter.BudgetExceededError):
            with usage_meter.owner_scope(db_session, strategy, "pipeline"):
                engine.run_all_steps(db_session, strategy)
        first = len(stub.calls)

        strategy.budget_micros = 10_000_000
        db_session.commit()
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            executed = engine.run_all_steps(db_session, strategy)

        assert executed == 72 - first, "resume continues; it never replays a paid step"
        assert _step_count(db_session, strategy) == 72
        assert usage_meter.spent_micros(db_session, strategy.id) == 72 * PER_CALL_MICROS

    def test_without_a_budget_the_pipeline_is_unchanged(
        self, db_session, product_with_strategy, monkeypatch
    ):
        strategy = _strategy(db_session, product_with_strategy, None)
        metered_client(monkeypatch)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            assert engine.run_all_steps(db_session, strategy) == 72


# ---------------------------------------------------------------------------
# The Celery tasks: a budget stop is a clean terminal-but-resumable state
# ---------------------------------------------------------------------------
class _NoCloseSession:
    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def close(self):
        pass


@pytest.fixture
def task_session(monkeypatch, db_session):
    monkeypatch.setattr("app.workers.tasks.SessionLocal", lambda: _NoCloseSession(db_session))
    return db_session


class TestTasks:
    def test_run_pipeline_ends_in_budget_exhausted_without_retrying(
        self, task_session, product_with_strategy, monkeypatch
    ):
        strategy = _strategy(task_session, product_with_strategy, 100_000)  # $0.10
        metered_client(monkeypatch)
        verify_started = []
        monkeypatch.setattr(run_verification, "delay", lambda *a, **k: verify_started.append(a))

        result = run_pipeline.apply(args=[str(strategy.id)], retries=0, throw=False)

        assert result.state == "SUCCESS", "a budget stop is an outcome, not a crash to retry"
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.BUDGET_EXHAUSTED
        assert "budget" in (strategy.error or "").lower()
        assert verify_started == [], "verification must not start on a half-built strategy"
        assert 0 < _step_count(task_session, strategy) < 72

    def test_run_verification_ends_in_budget_exhausted(
        self, task_session, product_with_strategy, monkeypatch
    ):
        strategy = _strategy(task_session, product_with_strategy, 100_000)
        strategy.status = StrategyStatus.VERIFYING
        task_session.commit()

        class _Out:
            def complete_json(self, **kw):
                raise usage_meter.BudgetExceededError("budget", budget_micros=1, spent_micros=1)

            complete = complete_json

        monkeypatch.setattr("app.verification.loop.get_client", lambda: _Out())

        result = run_verification.apply(args=[str(strategy.id)], retries=0, throw=False)

        assert result.state == "SUCCESS"
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.BUDGET_EXHAUSTED

    def test_verification_loop_does_not_swallow_the_budget_error(
        self, db_session, product_with_strategy, monkeypatch
    ):
        from app.verification.loop import run_verification_loop

        strategy = _strategy(db_session, product_with_strategy, 100_000)

        class _Out:
            def complete_json(self, **kw):
                raise usage_meter.BudgetExceededError("budget", budget_micros=1, spent_micros=1)

        monkeypatch.setattr("app.verification.loop.get_client", lambda: _Out())
        with pytest.raises(usage_meter.BudgetExceededError):
            run_verification_loop(db_session, strategy)


# ---------------------------------------------------------------------------
# The API: set it, bound it, read it, raise it, resume
# ---------------------------------------------------------------------------
class TestApi:
    def _post(self, client, product, **body):
        return client.post(f"/products/{product.id}/strategies", json=body)

    def test_explicit_budget_is_stored_and_returned(
        self, client, db_session, product_with_strategy
    ):
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS)
        resp = self._post(client, product, max_budget_usd=3)
        assert resp.status_code == 202, resp.text
        assert resp.json()["budget_usd"] == 3.0
        row = db_session.get(m.Strategy, uuid.UUID(resp.json()["id"]))
        assert row.budget_micros == 3_000_000

    def test_omitted_budget_uses_the_server_default(
        self, client, db_session, product_with_strategy, monkeypatch
    ):
        monkeypatch.setattr(settings, "pipeline_max_usd_default", 7.5)
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS)
        resp = self._post(client, product)
        assert resp.status_code == 202, resp.text
        assert resp.json()["budget_usd"] == 7.5

    @pytest.mark.parametrize("bad", [0, -1, 0.1, 51, 10_000])
    def test_out_of_range_budget_is_rejected(
        self, client, product_with_strategy, monkeypatch, bad
    ):
        monkeypatch.setattr(settings, "pipeline_max_usd_ceiling", 50.0)
        product, _ = product_with_strategy(m.FlowType.WITH_CLIENTS)
        resp = self._post(client, product, max_budget_usd=bad)
        assert resp.status_code == 422, resp.text

    def test_status_endpoint_reports_budget_and_spend(
        self, client, db_session, product_with_strategy
    ):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        strategy.budget_micros = 5_000_000
        db_session.commit()
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            usage_meter.note("anthropic", "x", 0, 100_000)  # $1.50
        body = client.get(f"/strategies/{strategy.id}").json()
        assert body["budget_usd"] == 5.0
        assert body["spent_usd"] == 1.5

    def test_resume_a_budget_exhausted_strategy_with_a_larger_budget(
        self, client, db_session, product_with_strategy, enqueued
    ):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        strategy.budget_micros = 3_000_000
        strategy.status = StrategyStatus.BUDGET_EXHAUSTED
        strategy.error = "budget reached"
        db_session.commit()

        resp = client.post(f"/strategies/{strategy.id}/resume", json={"max_budget_usd": 5})

        assert resp.status_code == 202, resp.text
        db_session.refresh(strategy)
        assert strategy.budget_micros == 5_000_000
        assert strategy.status is StrategyStatus.PENDING
        assert strategy.error is None
        assert enqueued == [str(strategy.id)]

    def test_resume_without_a_body_still_works(
        self, client, db_session, product_with_strategy, enqueued
    ):
        # the endpoint existed before the budget did; old callers send no body
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        strategy.status = StrategyStatus.RESEARCHING
        db_session.commit()
        assert client.post(f"/strategies/{strategy.id}/resume").status_code == 202
        assert enqueued == [str(strategy.id)]

    def test_new_budget_must_exceed_what_is_already_spent(
        self, client, db_session, product_with_strategy, enqueued
    ):
        _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
        strategy.budget_micros = 3_000_000
        strategy.status = StrategyStatus.BUDGET_EXHAUSTED
        db_session.commit()
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            usage_meter.note("anthropic", "x", 0, 200_000)  # $3.00 spent
        resp = client.post(f"/strategies/{strategy.id}/resume", json={"max_budget_usd": 2})
        assert resp.status_code == 422
        assert enqueued == []

    def test_another_accounts_strategy_is_not_found(self, client, db_session, enqueued):
        other = m.User(email="other@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user=other, name="P", description="d", type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                              status=StrategyStatus.BUDGET_EXHAUSTED, budget_micros=1_000_000)
        db_session.add(strategy)
        db_session.commit()

        resp = client.post(f"/strategies/{strategy.id}/resume", json={"max_budget_usd": 5})

        assert resp.status_code == 404
        db_session.refresh(strategy)
        assert strategy.budget_micros == 1_000_000, "a foreign strategy must not be changed"
        assert enqueued == []
