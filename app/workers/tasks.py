"""Celery tasks.

`run_pipeline` is idempotent and resumable by design: it asks the engine
for the next missing step every iteration, so re-enqueueing it after a
crash continues exactly where the last committed step left off (the DB's
unique constraint forbids duplicates regardless). When all steps exist it
assembles the documents and hands off to `run_verification`.
"""

import logging
import uuid as _uuid

from app.db.base import SessionLocal
from app.db.models import Strategy, StrategyStatus
from app.services.anthropic_client import is_permanent_error
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _pk(strategy_id):
    """Coerce the task's string argument to the UUID the column expects.

    Tasks are enqueued as `run_pipeline.delay(str(strategy.id))` — a string —
    while Strategy.id is a SQLAlchemy `Uuid` column. PostgreSQL accepts the
    string form, so this mismatch was invisible in production and in the live
    stack; SQLite (which the root suite runs on) raises
    "'str' object has no attribute 'hex'" instead. The task bodies had no unit
    coverage at all — conftest stubs `run_pipeline.delay` — so nothing ever
    exercised the difference. Coercing here is a no-op on PostgreSQL and makes
    the tasks backend-agnostic.
    """
    if isinstance(strategy_id, _uuid.UUID):
        return strategy_id
    try:
        return _uuid.UUID(str(strategy_id))
    except (ValueError, AttributeError, TypeError):
        return strategy_id


def _fail_strategy(session, strategy_id, exc: BaseException, *, why: str) -> None:
    """Move a strategy to the terminal FAILED state, recording the reason.

    StrategyStatus.FAILED existed in the enum, in the API's StrategyOut schema
    and in the frontend (types.ts declares it, badge.tsx renders a red badge
    for it) -- but NOTHING in app/ ever assigned it. Only RESEARCHING,
    VERIFYING and NEEDS_HUMAN_REVIEW were ever written, so a pipeline that gave
    up permanently left its strategy sitting in `researching` forever, showing
    the user an in-progress spinner for work that had stopped. Verified live on
    2026-08-20: three strategies were stuck that way, one of them for days
    carrying a 401 from a key that had since been revoked.

    `error` is the existing column for this -- no new field. It is the same one
    the retry path already wrote to, and GET /strategies/{id} already returns
    it, so the reason reaches the UI the moment the status does.
    """
    session.rollback()          # the caller's transaction is already poisoned
    strategy = session.get(Strategy, _pk(strategy_id))
    if strategy is None:
        return
    strategy.status = StrategyStatus.FAILED
    strategy.error = f"{type(exc).__name__}: {exc}"
    session.commit()
    logger.error(
        "strategy %s -> FAILED (%s): %s: %s",
        strategy_id, why, type(exc).__name__, exc,
    )


@celery_app.task(name="leadpilot.ping")
def ping() -> str:
    """Round-trip smoke test: verifies broker, worker and result backend."""
    return "pong"


@celery_app.task(name="leadpilot.run_pipeline", bind=True, max_retries=3)
def run_pipeline(self, strategy_id: str) -> str:
    from app.pipeline import engine  # local import keeps worker boot cheap

    session = SessionLocal()
    try:
        strategy = session.get(Strategy, _pk(strategy_id))
        if strategy is None:
            return f"strategy {strategy_id} not found"
        if strategy.status in (StrategyStatus.VERIFIED, StrategyStatus.NEEDS_HUMAN_REVIEW):
            return f"strategy {strategy_id} already finished ({strategy.status.value})"

        strategy.status = StrategyStatus.RESEARCHING
        strategy.error = None
        session.commit()

        executed = engine.run_all_steps(session, strategy)
        engine.assemble_documents(session, strategy)
        logger.info("strategy %s: pipeline complete (%s steps this run)", strategy_id, executed)

        # Bind the strategy to its playbook bucket now that Phase 2/3 research
        # exists. Every learning-loop query filters on pattern_key and nothing
        # used to write it, so playbook_scores stayed empty, auto-promotion
        # never ran and the Phase 6/8 playbook injection was always the "no
        # data yet" block -- see icp_extraction.ensure_pattern_key. Best
        # effort: a failure here must never fail an otherwise-good pipeline.
        try:
            from app.services.icp_extraction import (
                ensure_pattern_key,
                extract_icp_criteria,
            )

            ensure_pattern_key(session, strategy, extract_icp_criteria(session, strategy))
        except Exception:
            logger.exception("strategy %s: pattern_key assignment failed", strategy_id)
            session.rollback()

        strategy.status = StrategyStatus.VERIFYING
        session.commit()
        run_verification.delay(strategy_id)
        return f"pipeline complete ({executed} steps executed this run)"
    except Exception as exc:
        session.rollback()

        # Two ways to give up permanently, and both used to end in the same
        # silent limbo: status left at `researching` with nobody coming back.
        #
        #  1. The error can never succeed on retry (revoked key, exhausted
        #     credit balance, unknown model). Retrying it three times at 30s
        #     intervals just delays the inevitable by 90 seconds.
        #  2. Retries are exhausted. self.retry() would raise
        #     MaxRetriesExceededError, which nothing caught.
        permanent = is_permanent_error(exc)
        attempts_used = (self.request.retries or 0)
        exhausted = attempts_used >= (self.max_retries or 0)

        if permanent or exhausted:
            why = "non-retryable error" if permanent else                   f"retries exhausted after {attempts_used + 1} attempts"
            _fail_strategy(session, strategy_id, exc, why=why)
            # Re-raise rather than return: the task_failure signal in
            # app/workers/monitoring.py writes the task_errors row and alerts
            # admins, and it only fires on an actual failure. Raising plainly
            # (not self.retry) means Celery records FAILURE without another
            # attempt.
            raise

        strategy = session.get(Strategy, _pk(strategy_id))
        if strategy is not None:
            strategy.error = f"{type(exc).__name__}: {exc}"
            # Completed steps are already committed — a retry resumes.
            strategy.status = StrategyStatus.RESEARCHING
            session.commit()
        logger.exception("pipeline error on strategy %s — will retry/resume", strategy_id)
        raise self.retry(exc=exc, countdown=30)
    finally:
        session.close()


@celery_app.task(name="leadpilot.run_verification", bind=True, max_retries=3)
def run_verification(self, strategy_id: str) -> str:
    from app.verification.loop import run_verification_loop

    session = SessionLocal()
    try:
        strategy = session.get(Strategy, _pk(strategy_id))
        if strategy is None:
            return f"strategy {strategy_id} not found"
        final = run_verification_loop(session, strategy)
        return f"verification finished: {final.value}"
    except Exception as exc:
        session.rollback()

        # Same terminal-state fix as run_pipeline. A strategy that reaches
        # verification and then dies permanently used to sit at `verifying`
        # forever for exactly the same reason.
        permanent = is_permanent_error(exc)
        attempts_used = (self.request.retries or 0)
        exhausted = attempts_used >= (self.max_retries or 0)

        if permanent or exhausted:
            why = "non-retryable error" if permanent else                   f"retries exhausted after {attempts_used + 1} attempts"
            _fail_strategy(session, strategy_id, exc, why=why)
            raise

        logger.exception("verification error on strategy %s", strategy_id)
        raise self.retry(exc=exc, countdown=30)
    finally:
        session.close()
