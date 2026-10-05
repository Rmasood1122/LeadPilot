"""Approve a completed verification even when later runs were cut short.

Seen live on 2026-10-05: the first verification run walked all 10 checks (only
#1 factual accuracy failed; legal passed on its second attempt). Then three
more runs were started by Resume, each stopped part-way (budget, restart), and
the strategy sat in `verifying` with a worker that was no longer running. The
sign-off endpoint refused it (wrong status) and, read naively, the partial
runs' latest entries made the Legal check look failed.

The sign-off now:
  - is based on the latest COMPLETE run; partial runs after it are ignored;
  - is allowed from needs_human_review, budget_exhausted, and a `verifying`
    strategy that has gone quiet for 15 minutes (never while it may be running);
  - still never overrides Legal & compliance in the chosen run.
A stale redelivered verification task must not undo an approved strategy.
Offline.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.db import models as m
from app.db.models import StrategyStatus
from app.services import verification_override as vo
from app.verification.passes import build_passes
from app.workers import tasks as worker_tasks

REASON = "Checked the competitor names and prices by hand against vendor sites."
SPECS = build_passes(m.FlowType.WITH_CLIENTS)


def _row(spec, attempt, result, ts=None):
    return {"pass_no": spec.pass_no, "key": spec.key, "name": spec.name,
            "attempt": attempt, "result": result,
            "fix_description": "claim unverified" if result == "FAIL" else None,
            "fix_applied": False, **({"ts": ts} if ts else {})}


def _complete_run(failed=(1,), ts=None):
    rows = []
    for spec in SPECS:
        if spec.pass_no in failed:
            rows += [_row(spec, 1, "FAIL", ts), _row(spec, 2, "FAIL", ts)]
        else:
            rows.append(_row(spec, 1, "PASS", ts))
    return rows


def _partial_run(upto, failing_at=None, ts=None):
    rows = []
    for spec in SPECS[:upto]:
        rows.append(_row(spec, 1, "FAIL" if spec.pass_no == failing_at else "PASS", ts))
    return rows


def _strategy(db, product_with_strategy, log, status, age_minutes=0):
    _, s = product_with_strategy(m.FlowType.WITH_CLIENTS)
    s.status = status
    s.verified_passes_json = log
    s.updated_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    db.commit()
    return s


def _post(client, s, **over):
    body = {"pass_nos": [1], "reason": REASON, "acknowledge": True, **over}
    return client.post(f"/strategies/{s.id}/override-passes", json=body)


class TestRunSegmentation:
    def test_a_pass_number_going_backwards_starts_a_new_run(self):
        log = _complete_run() + _partial_run(3) + _partial_run(4)
        runs = vo.split_runs(log)
        assert [len(r) for r in runs] == [len(_complete_run()), 3, 4]

    def test_the_same_pass_starting_over_is_a_new_run(self):
        log = _partial_run(1) + _partial_run(1)
        assert len(vo.split_runs(log)) == 2

    def test_attempts_of_one_pass_stay_in_one_run(self):
        assert len(vo.split_runs(_complete_run(failed=(1, 6)))) == 1

    def test_latest_complete_run_ignores_partial_runs_after_it(self):
        full = _complete_run()
        run = vo.latest_complete_run(full + _partial_run(4, failing_at=4), 10)
        assert run == full

    def test_no_complete_run(self):
        assert vo.latest_complete_run(_partial_run(7), 10) is None


class TestApprovalFromTheCompletedRun:
    def test_stuck_verifying_with_partial_runs_after_a_complete_one(
        self, client, db_session, product_with_strategy
    ):
        # the live case: complete run (#1 failed) + partial runs where Legal
        # looked failed -- worker gone for 20 minutes
        log = (_complete_run() + _partial_run(4, failing_at=4)
               + _partial_run(3, failing_at=1))
        s = _strategy(db_session, product_with_strategy, log,
                      StrategyStatus.VERIFYING, age_minutes=20)
        resp = _post(client, s)
        assert resp.status_code == 200, resp.text
        db_session.refresh(s)
        assert s.status is StrategyStatus.VERIFIED
        entry = s.verified_passes_json[-1]
        assert entry["manual_override"] and entry["based_on_run"] == 1
        assert entry["pass_no"] == 1

    def test_budget_exhausted_is_allowed(self, client, db_session, product_with_strategy):
        log = _complete_run() + _partial_run(2)
        s = _strategy(db_session, product_with_strategy, log, StrategyStatus.BUDGET_EXHAUSTED)
        assert _post(client, s).status_code == 200

    def test_a_running_verification_is_never_signed_off(
        self, client, db_session, product_with_strategy
    ):
        log = _complete_run() + _partial_run(3)
        s = _strategy(db_session, product_with_strategy, log,
                      StrategyStatus.VERIFYING, age_minutes=2)
        resp = _post(client, s)
        assert resp.status_code == 409
        assert "may still be running" in resp.json()["detail"]
        db_session.refresh(s)
        assert s.status is StrategyStatus.VERIFYING

    def test_recent_log_activity_counts_as_running(
        self, client, db_session, product_with_strategy
    ):
        recent = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
        log = _complete_run() + _partial_run(3, ts=recent)
        s = _strategy(db_session, product_with_strategy, log,
                      StrategyStatus.VERIFYING, age_minutes=60)
        assert _post(client, s).status_code == 409

    def test_no_complete_run_means_nothing_to_sign_off(
        self, client, db_session, product_with_strategy
    ):
        s = _strategy(db_session, product_with_strategy, _partial_run(7, failing_at=1),
                      StrategyStatus.NEEDS_HUMAN_REVIEW)
        resp = _post(client, s)
        assert resp.status_code == 409
        assert "complete verification run" in resp.json()["detail"]

    def test_legal_failure_in_the_chosen_run_still_blocks(
        self, client, db_session, product_with_strategy
    ):
        s = _strategy(db_session, product_with_strategy, _complete_run(failed=(1, 4)),
                      StrategyStatus.VERIFYING, age_minutes=30)
        resp = _post(client, s, pass_nos=[1, 4])
        assert resp.status_code == 409 and "Legal" in resp.json()["detail"]
        db_session.refresh(s)
        assert s.status is StrategyStatus.VERIFYING

    @pytest.mark.parametrize("status", [
        StrategyStatus.VERIFIED, StrategyStatus.RESEARCHING, StrategyStatus.PENDING,
        StrategyStatus.FAILED, StrategyStatus.EXECUTING,
    ])
    def test_other_statuses_still_refused(self, client, db_session,
                                          product_with_strategy, status):
        s = _strategy(db_session, product_with_strategy, _complete_run(), status,
                      age_minutes=60)
        assert _post(client, s).status_code == 409


class TestStaleTaskCannotUndoApproval:
    def test_verification_task_skips_a_verified_strategy(self, monkeypatch):
        import contextlib
        import types

        import app.verification.loop as vloop
        from app.services import usage_meter

        ran = []

        class _Session:
            def get(self, *_a):
                return types.SimpleNamespace(status=StrategyStatus.VERIFIED)

            def close(self):
                pass

        monkeypatch.setattr(worker_tasks, "SessionLocal", lambda: _Session())
        monkeypatch.setattr(vloop, "run_verification_loop",
                            lambda *a, **k: ran.append(1))
        monkeypatch.setattr(usage_meter, "owner_scope",
                            lambda *a, **k: contextlib.nullcontext())
        out = worker_tasks.run_verification.run("00000000-0000-0000-0000-000000000001")
        assert ran == []
        assert "already verified" in out
