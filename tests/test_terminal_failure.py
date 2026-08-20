"""A pipeline that gives up must land in FAILED — never sit in limbo.

Reproduces two defects found during the 2026-08-20 full-stack verification:

  Finding 1  StrategyStatus.FAILED existed in the enum, in StrategyStatusOut,
             in the frontend's types.ts and in badge.tsx (which renders a red
             badge for it) -- and NOTHING in app/ ever assigned it. A pipeline
             that permanently gave up left the strategy at `researching`, so
             the UI showed an in-progress spinner forever. Three strategies
             were stuck that way in the live database, one for days.

  Finding 2  The gateway already knew a revoked key or an exhausted credit
             balance can never succeed on retry (those errors are absent from
             RETRYABLE_API_ERRORS), but the Celery layer retried EVERY
             exception, so a permanent failure burned all three attempts at
             30s intervals before giving up into the limbo above.

Every test here runs against fakes. No Anthropic call is made.
"""

import anthropic
import httpx
import pytest

from app.db import models as m
from app.db.models import StrategyStatus
from app.services.anthropic_client import (
    PERMANENT_API_ERRORS,
    RETRYABLE_API_ERRORS,
    TruncatedResponseError,
    is_permanent_error,
)
from app.workers.tasks import run_pipeline, run_verification


def _api_error(cls, status):
    """Build a real SDK exception instance without touching the network."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls("boom", response=response, body=None)


def credit_exhausted():
    return _api_error(anthropic.BadRequestError, 400)


def revoked_key():
    return _api_error(anthropic.AuthenticationError, 401)


def rate_limited():
    return _api_error(anthropic.RateLimitError, 429)


def overloaded():
    return _api_error(anthropic.OverloadedError, 529)


def _raises(exc_factory):
    """A stand-in callable that raises instead of doing the real work."""

    def _boom(*args, **kwargs):
        raise exc_factory()

    return _boom


class _NoCloseSession:
    """tasks.py closes its session in `finally`; the fixture session must survive."""

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        return getattr(self._real, name)

    def close(self):
        pass


class _NoopTask:
    """Stands in for run_verification.delay() so the handoff is a no-op."""

    def delay(self, *args, **kwargs):
        return None


class RetryAttempted(Exception):
    """Sentinel: the task asked Celery for another attempt."""


def _spy_on_retry(monkeypatch, task):
    """Replace task.retry() with a sentinel raise.

    Celery's EAGER mode re-executes the task inline on retry until max_retries
    is spent, so `apply()` can never show an intermediate RETRY state — a
    retryable error would run to exhaustion and land in FAILED, making
    "retries" and "does not retry" look identical. Spying on the retry call
    itself is what actually distinguishes them.
    """

    def _fake_retry(*args, **kwargs):
        raise RetryAttempted()

    monkeypatch.setattr(task, "retry", _fake_retry)


@pytest.fixture
def task_session(monkeypatch, db_session):
    """Point both tasks at the test session.

    tasks.py does `from app.db.base import SessionLocal` at import time, so
    patching app.db.base.SessionLocal would NOT affect it — the name in
    app.workers.tasks is already bound.
    """
    monkeypatch.setattr(
        "app.workers.tasks.SessionLocal", lambda: _NoCloseSession(db_session)
    )
    return db_session


def _strategy(db_session, product_with_strategy, status=StrategyStatus.RESEARCHING):
    _, strategy = product_with_strategy(m.FlowType.WITH_CLIENTS)
    strategy.status = status
    db_session.commit()
    return strategy


# ---------------------------------------------------------------------------
# Classification (Finding 2)
# ---------------------------------------------------------------------------
class TestErrorClassification:
    @pytest.mark.parametrize("make", [credit_exhausted, revoked_key])
    def test_permanent_errors_are_permanent(self, make):
        assert is_permanent_error(make()) is True

    @pytest.mark.parametrize("make", [rate_limited, overloaded])
    def test_retryable_errors_are_not_permanent(self, make):
        assert is_permanent_error(make()) is False

    def test_truncation_is_permanent(self):
        # Retrying an identical request against an identical ceiling truncates
        # identically — raising the ceiling is the caller's job.
        assert is_permanent_error(TruncatedResponseError("x", limit=8000)) is True

    def test_unknown_errors_keep_retrying(self):
        # Conservative default: a wrong "permanent" verdict would turn a
        # recoverable blip into a dead strategy.
        assert is_permanent_error(ValueError("who knows")) is False
        assert is_permanent_error(RuntimeError("transient")) is False

    def test_overloaded_529_is_retryable(self):
        # 529 is NOT a subclass of InternalServerError; listing only 5xx left
        # the single most retryable response the API sends unretried.
        assert isinstance(overloaded(), RETRYABLE_API_ERRORS)

    def test_classifications_are_disjoint(self):
        assert not (set(RETRYABLE_API_ERRORS) & set(PERMANENT_API_ERRORS))


# ---------------------------------------------------------------------------
# run_pipeline (Findings 1 + 2)
# ---------------------------------------------------------------------------
class TestPipelineTerminalState:
    @pytest.mark.parametrize("make", [credit_exhausted, revoked_key])
    def test_permanent_error_fails_immediately(
        self, monkeypatch, task_session, product_with_strategy, make
    ):
        strategy = _strategy(task_session, product_with_strategy)
        monkeypatch.setattr("app.pipeline.engine.run_all_steps", _raises(make))

        result = run_pipeline.apply(args=[str(strategy.id)], retries=0, throw=False)

        # Finding 2: failed on the FIRST attempt, no retry scheduled.
        assert result.state == "FAILURE", "a permanent error must not be retried"
        # Finding 1: terminal state, not limbo.
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.FAILED
        assert strategy.status is not StrategyStatus.RESEARCHING
        assert strategy.error, "the reason must be recorded"

    @pytest.mark.parametrize("make", [rate_limited, overloaded])
    def test_retryable_error_still_retries(
        self, monkeypatch, task_session, product_with_strategy, make
    ):
        strategy = _strategy(task_session, product_with_strategy)
        monkeypatch.setattr("app.pipeline.engine.run_all_steps", _raises(make))
        _spy_on_retry(monkeypatch, run_pipeline)

        result = run_pipeline.apply(args=[str(strategy.id)], retries=0, throw=False)

        assert isinstance(result.result, RetryAttempted), (
            "transient errors must still go through Celery's retry"
        )
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.RESEARCHING, (
            "a retryable failure stays resumable, not terminal"
        )
        assert strategy.status is not StrategyStatus.FAILED

    @pytest.mark.parametrize("make", [credit_exhausted, revoked_key])
    def test_permanent_error_never_calls_retry(
        self, monkeypatch, task_session, product_with_strategy, make
    ):
        """The other half of the distinction: retry must not even be attempted."""
        strategy = _strategy(task_session, product_with_strategy)
        monkeypatch.setattr("app.pipeline.engine.run_all_steps", _raises(make))
        _spy_on_retry(monkeypatch, run_pipeline)

        result = run_pipeline.apply(args=[str(strategy.id)], retries=0, throw=False)

        assert not isinstance(result.result, RetryAttempted), (
            "a permanent error must fail fast, not burn a retry"
        )
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.FAILED

    def test_retry_exhaustion_lands_in_failed(
        self, monkeypatch, task_session, product_with_strategy
    ):
        strategy = _strategy(task_session, product_with_strategy)
        monkeypatch.setattr("app.pipeline.engine.run_all_steps", _raises(rate_limited))

        # Retryable error, but the last attempt is used up: self.retry() would
        # raise MaxRetriesExceededError, which nothing caught.
        result = run_pipeline.apply(
            args=[str(strategy.id)], retries=run_pipeline.max_retries, throw=False
        )

        assert result.state == "FAILURE"
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.FAILED
        assert strategy.error

    def test_failed_strategy_is_resumable(
        self, monkeypatch, task_session, product_with_strategy
    ):
        """FAILED is terminal-but-retryable: top up credits, then resume."""
        strategy = _strategy(task_session, product_with_strategy)
        monkeypatch.setattr(
            "app.pipeline.engine.run_all_steps", _raises(credit_exhausted)
        )
        run_pipeline.apply(args=[str(strategy.id)], retries=0, throw=False)
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.FAILED

        # run_pipeline refuses only VERIFIED / NEEDS_HUMAN_REVIEW, so a FAILED
        # strategy re-runs and resumes from its last committed step.
        calls = []

        def _ok(*args, **kwargs):
            calls.append(1)
            return 0

        monkeypatch.setattr("app.pipeline.engine.run_all_steps", _ok)
        monkeypatch.setattr(
            "app.pipeline.engine.assemble_documents", lambda *a, **k: None
        )
        monkeypatch.setattr("app.workers.tasks.run_verification", _NoopTask())
        run_pipeline.apply(args=[str(strategy.id)], retries=0, throw=False)
        assert calls, "a FAILED strategy must still be resumable"


# ---------------------------------------------------------------------------
# run_verification (Finding 1)
# ---------------------------------------------------------------------------
class TestVerificationTerminalState:
    def test_permanent_error_fails_immediately(
        self, monkeypatch, task_session, product_with_strategy
    ):
        strategy = _strategy(
            task_session, product_with_strategy, StrategyStatus.VERIFYING
        )
        monkeypatch.setattr(
            "app.verification.loop.run_verification_loop", _raises(revoked_key)
        )

        result = run_verification.apply(args=[str(strategy.id)], retries=0, throw=False)

        assert result.state == "FAILURE"
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.FAILED
        assert strategy.status is not StrategyStatus.VERIFYING, (
            "verification limbo is the same bug as pipeline limbo"
        )
        assert strategy.error

    def test_retryable_error_still_retries(
        self, monkeypatch, task_session, product_with_strategy
    ):
        strategy = _strategy(
            task_session, product_with_strategy, StrategyStatus.VERIFYING
        )
        monkeypatch.setattr(
            "app.verification.loop.run_verification_loop", _raises(overloaded)
        )
        _spy_on_retry(monkeypatch, run_verification)

        result = run_verification.apply(args=[str(strategy.id)], retries=0, throw=False)

        assert isinstance(result.result, RetryAttempted)
        task_session.refresh(strategy)
        assert strategy.status is not StrategyStatus.FAILED

    def test_permanent_error_never_calls_retry(
        self, monkeypatch, task_session, product_with_strategy
    ):
        strategy = _strategy(
            task_session, product_with_strategy, StrategyStatus.VERIFYING
        )
        monkeypatch.setattr(
            "app.verification.loop.run_verification_loop", _raises(credit_exhausted)
        )
        _spy_on_retry(monkeypatch, run_verification)

        result = run_verification.apply(args=[str(strategy.id)], retries=0, throw=False)

        assert not isinstance(result.result, RetryAttempted)
        task_session.refresh(strategy)
        assert strategy.status is StrategyStatus.FAILED
