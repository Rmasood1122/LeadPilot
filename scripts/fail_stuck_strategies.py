"""One-off cleanup: move permanently-stuck strategies to the terminal FAILED state.

WHY
    StrategyStatus.FAILED existed in the enum, in StrategyStatusOut, in the
    frontend's types.ts and in badge.tsx (which renders a red badge for it) --
    and nothing in app/ ever assigned it. Only RESEARCHING, VERIFYING and
    NEEDS_HUMAN_REVIEW were ever written. A pipeline that gave up permanently
    therefore left its strategy sitting in `researching` forever, showing the
    owner an in-progress spinner for work that had stopped days earlier.

    app/workers/tasks.py now sets FAILED at both give-up points (non-retryable
    error, retries exhausted), but that only helps strategies that fail from
    now on. The rows already stranded need this pass.

WHAT COUNTS AS STUCK
    status in (researching, verifying) AND idle longer than --min-idle-hours.

    The idle window is the whole safety mechanism: a strategy that is genuinely
    mid-run touches updated_at as each step commits, so a live pipeline is
    never a candidate. The default of 1 hour is far beyond any real step, and
    pipeline_step_timeout_seconds is 300s.

    Two distinct populations show up here, and they get different reasons:

      * error IS set -- the task caught an exception and recorded it before
        dying into limbo. The recorded error is the honest cause and is kept
        verbatim, with a note that it was reclassified retroactively.

      * error IS NULL -- the worker was killed mid-run (SIGKILL, container
        eviction, host restart), so no Python-level handler ever ran. Nothing
        inside the task can catch this, by definition; it is what
        monitoring.detect_stale_pipeline_steps exists to notice, and that is
        deliberately detection-only. These get an honest "cause unrecorded".

NOTHING IS LOST
    FAILED is terminal but not final: run_pipeline refuses only VERIFIED and
    NEEDS_HUMAN_REVIEW, so POST /strategies/{id}/resume still restarts a FAILED
    strategy and the engine resumes from its last committed step. Completed
    research steps are untouched by this script.

USAGE
    python -m scripts.fail_stuck_strategies                 # dry run (default)
    python -m scripts.fail_stuck_strategies --apply
    python -m scripts.fail_stuck_strategies --apply --min-idle-hours 6
"""

from __future__ import annotations

import argparse
import datetime

from sqlalchemy import func

from app.db.base import SessionLocal
from app.db.models import ResearchStep, Strategy, StrategyStatus

STUCK_STATUSES = (StrategyStatus.RESEARCHING, StrategyStatus.VERIFYING)

RECLASSIFIED = "[reclassified {stamp}: strategy was stranded in '{status}' before the terminal-state fix]"
NO_CAUSE = (
    "Worker died mid-run without recording an error (killed process, container "
    "eviction or host restart -- no exception handler ran). "
) + RECLASSIFIED


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _idle_for(strategy: Strategy, now: datetime.datetime) -> datetime.timedelta:
    updated = strategy.updated_at
    if updated.tzinfo is None:  # SQLite / naive columns
        updated = updated.replace(tzinfo=datetime.timezone.utc)
    return now - updated


def find_stuck(session, min_idle_hours: float) -> list[tuple[Strategy, datetime.timedelta, int]]:
    now = _utcnow()
    cutoff = datetime.timedelta(hours=min_idle_hours)
    rows = []
    for strategy in (
        session.query(Strategy)
        .filter(Strategy.status.in_(STUCK_STATUSES))
        .order_by(Strategy.created_at)
    ):
        idle = _idle_for(strategy, now)
        if idle < cutoff:
            continue  # still plausibly alive — never touch a running pipeline
        steps = (
            session.query(func.count(ResearchStep.id))
            .filter(ResearchStep.strategy_id == strategy.id)
            .scalar()
        )
        rows.append((strategy, idle, steps))
    return rows


def build_reason(strategy: Strategy) -> str:
    stamp = _utcnow().strftime("%Y-%m-%d")
    note = RECLASSIFIED.format(stamp=stamp, status=strategy.status.value)
    existing = (strategy.error or "").strip()
    if existing:
        return f"{existing}  {note}"
    return NO_CAUSE.format(stamp=stamp, status=strategy.status.value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="write the changes (default: dry run)"
    )
    parser.add_argument(
        "--min-idle-hours",
        type=float,
        default=1.0,
        help="only touch strategies idle at least this long (default: 1.0)",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        stuck = find_stuck(session, args.min_idle_hours)
        if not stuck:
            print(f"No strategies stuck for >= {args.min_idle_hours}h. Nothing to do.")
            return 0

        mode = "APPLYING" if args.apply else "DRY RUN (pass --apply to write)"
        print(f"{mode} — {len(stuck)} stuck strateg{'y' if len(stuck) == 1 else 'ies'}\n")
        print(f"{'id':10} {'status':14} {'steps':>5} {'idle':>16}  cause")
        print("-" * 100)

        for strategy, idle, steps in stuck:
            cause = "recorded error" if (strategy.error or "").strip() else "NO error recorded"
            print(
                f"{str(strategy.id)[:8]:10} {strategy.status.value:14} {steps:>5} "
                f"{str(idle).split('.')[0]:>16}  {cause}"
            )
            if args.apply:
                strategy.error = build_reason(strategy)
                strategy.status = StrategyStatus.FAILED

        if args.apply:
            session.commit()
            print(f"\nCommitted: {len(stuck)} -> FAILED.")
            print("These remain resumable via POST /strategies/{id}/resume.")
        else:
            session.rollback()
            print("\nDry run — nothing written.")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
