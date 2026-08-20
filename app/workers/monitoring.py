"""
Background job monitoring.

1. Celery task_failure signal → writes to task_errors table + admin FCM for critical tasks
2. Stale pipeline step detection — run inside the nightly job (or separately)
3. Queue-depth and worker stats helpers (used by /admin/celery-stats endpoint)

Critical tasks (get FCM notification on failure):
  - Any task in CRITICAL_TASK_NAMES (pipeline steps, nightly aggregation, send tasks)

Non-critical tasks (logged to task_errors only, no FCM):
  - Minor utility tasks, health checks, cache warmup
"""
from __future__ import annotations

import datetime
import traceback
from typing import Any

from app.core.logging import get_logger

logger = get_logger("workers.monitoring")

# ---------------------------------------------------------------------------
# Tasks that trigger admin FCM notification on failure
# ---------------------------------------------------------------------------

CRITICAL_TASK_NAMES: frozenset[str] = frozenset({
    "app.workers.pipeline_tasks.execute_pipeline_step",
    "app.workers.pipeline_tasks.run_pipeline",
    "app.workers.pipeline_tasks.run_verification",
    "app.workers.outreach_tasks.send_sequence_step",
    "app.workers.outreach_tasks.run_sequence",
    "app.workers.learning_tasks.run_strategy_aggregation",
    "app.workers.learning_tasks.auto_promote_winners",
    "app.workers.lead_tasks.source_leads",
})


def register_task_failure_signal() -> None:
    """
    Register the task_failure Celery signal. Call once during Celery worker startup.
    This is typically called in the celery_app.py module or in on_after_configure hooks.
    """
    from app.workers.celery_app import celery_app
    from celery.signals import task_failure

    @task_failure.connect
    def on_task_failure(
        sender: Any = None,
        task_id: str = "",
        exception: Exception | None = None,
        args: tuple = (),
        kwargs: dict = {},
        traceback: Any = None,
        einfo: Any = None,
        **extra: Any,
    ) -> None:
        task_name = sender.name if sender else "unknown"
        _handle_task_failure(
            task_id=task_id,
            task_name=task_name,
            args=args,
            kwargs=kwargs,
            exception=exception,
            tb_str=str(einfo) if einfo else "",
        )


def _handle_task_failure(
    task_id: str,
    task_name: str,
    args: tuple,
    kwargs: dict,
    exception: Exception | None,
    tb_str: str,
) -> None:
    """Write task_errors row and optionally send admin FCM."""
    error_type = type(exception).__name__ if exception else "Unknown"
    error_message = str(exception) if exception else ""

    # Summarize args safely (avoid logging sensitive data)
    args_summary = _safe_args_summary(args, kwargs)

    logger.error(
        "celery_task_failed",
        task_id=task_id,
        task_name=task_name,
        error_type=error_type,
        error_message=error_message,
        args_summary=args_summary,
    )

    # Write to task_errors table
    try:
        from app.core.database import SessionLocal
        from app.models.task_error import TaskError

        db = SessionLocal()
        try:
            db.add(TaskError(
                task_name=task_name,
                task_id=task_id,
                args_summary=args_summary,
                error_type=error_type,
                error_message=error_message[:2000],  # truncate
                traceback=tb_str[:5000],
                ts=datetime.datetime.utcnow(),
            ))
            db.commit()
        finally:
            db.close()
    except Exception as write_err:
        logger.error("monitoring.task_error_write_failed", error=str(write_err))

    # FCM notification for critical tasks
    if task_name in CRITICAL_TASK_NAMES:
        _send_admin_failure_notification(task_name, error_type, error_message)


def _send_admin_failure_notification(task_name: str, error_type: str, message: str) -> None:
    """Send FCM to all admin users for critical task failures."""
    import threading

    def _send() -> None:
        try:
            import asyncio
            from app.services.notification_service import NotificationService
            asyncio.run(NotificationService.send_to_admins(
                title="Background Task Failed",
                body=f"{task_name.split('.')[-1]} failed: {error_type} — check /admin/task-errors",
                data={"event": "task_failure", "task_name": task_name, "error_type": error_type},
            ))
        except Exception as e:
            logger.error("monitoring.fcm_admin_notify_failed", error=str(e))

    threading.Thread(target=_send, daemon=True).start()


def _safe_args_summary(args: tuple, kwargs: dict) -> str:
    """Build a safe, non-sensitive summary of task arguments."""
    safe_args = []
    for a in args:
        if isinstance(a, str) and len(a) < 200:
            safe_args.append(a)
        elif isinstance(a, (int, float, bool)):
            safe_args.append(str(a))
        else:
            safe_args.append(f"<{type(a).__name__}>")
    safe_kwargs = {k: v for k, v in kwargs.items() if k in (
        "strategy_id", "lead_id", "user_id", "step_no", "flow_type", "variant"
    )}
    return f"args={safe_args} kwargs={safe_kwargs}"


# ---------------------------------------------------------------------------
# Stale pipeline step detection
# ---------------------------------------------------------------------------

def detect_stale_pipeline_steps() -> list[dict[str, Any]]:
    """
    Detect stalled pipeline runs.

    INTEGRATION REPAIR NOTE: the delivered M8-C4 version filtered
    ResearchStep.status == "in_progress", but the M1 engine has no status
    column — a research_steps row is written only when a step COMPLETES
    (row presence is the resumability contract). "Stalled" is therefore a
    property of the STRATEGY: status researching/verifying, but its newest
    completed step is older than PIPELINE_STEP_TIMEOUT_MINUTES.

    Detection-only: strategies are flagged and logged, never mutated —
    the M1 engine owns strategy status transitions.
    """
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models.research_step import ResearchStep
    from app.models.strategy import Strategy

    timeout_minutes = settings.PIPELINE_STEP_TIMEOUT_MINUTES
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=timeout_minutes)

    db = SessionLocal()
    stalled = []
    try:
        from sqlalchemy import func as sa_func

        latest_step = (
            db.query(
                ResearchStep.strategy_id.label("sid"),
                sa_func.max(ResearchStep.created_at).label("last_step_at"),
                sa_func.max(ResearchStep.step_no).label("last_step_no"),
            )
            .group_by(ResearchStep.strategy_id)
            .subquery()
        )
        rows = (
            db.query(Strategy.id, latest_step.c.last_step_at, latest_step.c.last_step_no)
            .outerjoin(latest_step, latest_step.c.sid == Strategy.id)
            .filter(Strategy.status.in_(["researching", "verifying"]))
            .all()
        )
        for sid, last_step_at, last_step_no in rows:
            anchor = last_step_at  # None => started but no step ever completed
            if anchor is not None and anchor.tzinfo is not None:
                anchor = anchor.replace(tzinfo=None)
            if anchor is None or anchor <= cutoff:
                stalled.append({
                    "strategy_id": str(sid),
                    "last_step_no": last_step_no,
                    "last_step_at": last_step_at.isoformat() if last_step_at else None,
                })
                logger.error(
                    "pipeline_run_stalled",
                    strategy_id=str(sid),
                    last_step_no=last_step_no,
                    stuck_minutes=timeout_minutes,
                )
    except Exception as e:
        logger.error("monitoring.stale_detection_failed", error=str(e))
        db.rollback()
    finally:
        db.close()

    if stalled:
        logger.warning(
            "stale_runs_flagged",
            count=len(stalled),
            strategy_ids=[s["strategy_id"] for s in stalled],
        )

    return stalled


# ---------------------------------------------------------------------------
# Queue depth and worker stats (used by /admin/celery-stats)
# ---------------------------------------------------------------------------

def get_celery_stats() -> dict[str, Any]:
    """
    Return current queue depths and active worker count.
    Uses Celery inspect + Redis LLEN for queue depths.
    # TODO: verify queue name configuration matches your celery_app.py task_routes
    """
    from app.workers.celery_app import celery_app

    stats: dict[str, Any] = {
        "queues": {},
        "active_workers": 0,
        "tasks_processed_last_hour": None,
    }

    # Queue depths via Redis
    try:
        from app.core.redis_client import get_sync_redis
        redis = get_sync_redis()
        for queue_name in ["pipeline", "outreach", "learning", "default"]:
            depth = redis.llen(queue_name)
            stats["queues"][queue_name] = {"depth": depth}
    except Exception as e:
        logger.warning("monitoring.queue_depth_failed", error=str(e))

    # Active workers via Celery inspect
    try:
        inspector = celery_app.control.inspect(timeout=2.0)
        active = inspector.active()
        if active:
            stats["active_workers"] = len(active)
            total_active_tasks = sum(len(tasks) for tasks in active.values())
            stats["active_tasks"] = total_active_tasks
        else:
            stats["active_workers"] = 0
            stats["active_tasks"] = 0
    except Exception as e:
        logger.warning("monitoring.celery_inspect_failed", error=str(e))

    return stats
