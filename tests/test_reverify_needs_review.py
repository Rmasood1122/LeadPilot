"""A strategy in `needs_human_review` can be re-verified without redoing research.

Seen live on 2026-10-05: a $3 run finished all 32 research steps, then pass 1
(factual accuracy) failed twice -- the reduced-plan cap -- and the strategy
landed in `needs_human_review`. That state was a dead end: POST /resume returns
409 for it, run_pipeline refuses it, and nothing else starts verification. The
only way forward was a new strategy and a second payment for the same research.

POST /strategies/{id}/reverify runs the ten passes again on the existing
research. It never marks anything verified itself: the judge decides, and a
pass that keeps failing keeps the strategy in needs_human_review.
Offline: the Celery publish is stubbed, the judge is the repo's FakeClaude.
"""

import uuid

import pytest

from app.config import settings
from app.db import models as m
from app.db.models import StrategyStatus
from app.verification.loop import run_verification_loop
from app.workers import tasks as worker_tasks


@pytest.fixture()
def verify_jobs(monkeypatch):
    jobs = []
    monkeypatch.setattr(worker_tasks.run_verification, "delay",
                        lambda *a: jobs.append(a))
    return jobs


def _review_strategy(db, product_with_strategy, *, steps_per_phase=2):
    _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
    strategy.status = StrategyStatus.NEEDS_HUMAN_REVIEW
    strategy.steps_per_phase = steps_per_phase
    strategy.budget_micros = 3_000_000
    strategy.strategy_document = "# Strategy\nTarget fire-protection owners."
    db.commit()
    return strategy


class TestEndpoint:
    def test_requeues_verification_and_reports_verifying(
        self, client, db_session, product_with_strategy, verify_jobs
    ):
        strategy = _review_strategy(db_session, product_with_strategy)
        resp = client.post(f"/strategies/{strategy.id}/reverify",
                           json={"max_budget_usd": 6, "max_attempts": 4})
        assert resp.status_code == 202, resp.text
        db_session.refresh(strategy)
        assert strategy.status is StrategyStatus.VERIFYING
        assert strategy.budget_micros == 6_000_000
        assert verify_jobs == [(str(strategy.id), 4)]

    def test_works_without_a_body(self, client, db_session, product_with_strategy,
                                  verify_jobs):
        strategy = _review_strategy(db_session, product_with_strategy)
        assert client.post(f"/strategies/{strategy.id}/reverify").status_code == 202
        assert verify_jobs == [(str(strategy.id), None)]

    @pytest.mark.parametrize("status", [
        StrategyStatus.VERIFIED, StrategyStatus.PENDING, StrategyStatus.RESEARCHING,
        StrategyStatus.VERIFYING, StrategyStatus.FAILED, StrategyStatus.EXECUTING,
    ])
    def test_refused_unless_waiting_for_human_review(
        self, client, db_session, product_with_strategy, verify_jobs, status
    ):
        strategy = _review_strategy(db_session, product_with_strategy)
        strategy.status = status
        db_session.commit()
        resp = client.post(f"/strategies/{strategy.id}/reverify")
        assert resp.status_code == 409
        db_session.refresh(strategy)
        assert strategy.status is status
        assert verify_jobs == []

    @pytest.mark.parametrize("attempts", [0, 6, -1])
    def test_attempt_count_is_bounded(self, client, db_session,
                                      product_with_strategy, verify_jobs, attempts):
        strategy = _review_strategy(db_session, product_with_strategy)
        resp = client.post(f"/strategies/{strategy.id}/reverify",
                           json={"max_attempts": attempts})
        assert resp.status_code == 422
        assert verify_jobs == []

    def test_new_budget_must_exceed_what_is_spent(
        self, client, db_session, product_with_strategy, verify_jobs
    ):
        from app.services import usage_meter
        strategy = _review_strategy(db_session, product_with_strategy)
        with usage_meter.owner_scope(db_session, strategy, "pipeline"):
            usage_meter.note("anthropic", "x", 0, 200_000)  # $3.00
        resp = client.post(f"/strategies/{strategy.id}/reverify",
                           json={"max_budget_usd": 2})
        assert resp.status_code == 422
        db_session.refresh(strategy)
        assert strategy.status is StrategyStatus.NEEDS_HUMAN_REVIEW
        assert verify_jobs == []

    def test_another_accounts_strategy_is_not_found(self, client, db_session,
                                                    verify_jobs):
        other = m.User(email="other-rv@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.flush()
        product = m.Product(user=other, name="P", description="d",
                            type=m.ProductType.SKILL)
        db_session.add(product)
        db_session.flush()
        strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS,
                              status=StrategyStatus.NEEDS_HUMAN_REVIEW)
        db_session.add(strategy)
        db_session.commit()
        resp = client.post(f"/strategies/{strategy.id}/reverify")
        assert resp.status_code == 404
        db_session.refresh(strategy)
        assert strategy.status is StrategyStatus.NEEDS_HUMAN_REVIEW
        assert verify_jobs == []


class TestLoopOverride:
    def test_reduced_plan_cap_applies_by_default(
        self, db_session, fake_claude, product_with_strategy
    ):
        strategy = _review_strategy(db_session, product_with_strategy)
        fake_claude.judge_script[1] = [("FAIL", "claim X is unverified")] * 5
        final = run_verification_loop(db_session, strategy)
        assert final is StrategyStatus.NEEDS_HUMAN_REVIEW
        assert len([e for e in strategy.verified_passes_json if e["pass_no"] == 1]) == 2

    def test_override_allows_more_attempts_and_can_reach_verified(
        self, db_session, fake_claude, product_with_strategy
    ):
        strategy = _review_strategy(db_session, product_with_strategy)
        fake_claude.judge_script[1] = [("FAIL", "claim X is unverified")] * 2 + [("PASS", None)]
        final = run_verification_loop(db_session, strategy, max_attempts=3)
        assert final is StrategyStatus.VERIFIED
        p1 = [e for e in strategy.verified_passes_json if e["pass_no"] == 1]
        assert [e["result"] for e in p1] == ["FAIL", "FAIL", "PASS"]

    def test_override_never_turns_a_failing_pass_into_a_pass(
        self, db_session, fake_claude, product_with_strategy
    ):
        strategy = _review_strategy(db_session, product_with_strategy)
        fake_claude.judge_script[1] = [("FAIL", "claim X is unverified")] * 5
        final = run_verification_loop(db_session, strategy, max_attempts=5)
        assert final is StrategyStatus.NEEDS_HUMAN_REVIEW
        assert strategy.status is StrategyStatus.NEEDS_HUMAN_REVIEW

    def test_task_forwards_the_override(self, monkeypatch):
        """The Celery task passes max_attempts to the loop (no DB: stub session)."""
        import contextlib
        import types

        import app.verification.loop as vloop
        from app.services import usage_meter

        seen = {}

        class _Session:
            def get(self, *_a):
                return types.SimpleNamespace()

            def close(self):
                pass

        def spy(session, strategy, max_attempts=None):
            seen["n"] = max_attempts
            return StrategyStatus.VERIFIED

        monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: _Session())
        monkeypatch.setattr(vloop, "run_verification_loop", spy)
        monkeypatch.setattr(usage_meter, "owner_scope",
                            lambda *a, **k: contextlib.nullcontext())
        worker_tasks.run_verification.run(str(uuid.uuid4()), 4)
        assert seen["n"] == 4
