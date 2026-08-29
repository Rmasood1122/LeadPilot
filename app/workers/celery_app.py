"""Celery application shared by the worker and beat containers.

Start worker:  celery -A app.workers.celery_app worker --loglevel=INFO
Start beat:    celery -A app.workers.celery_app beat   --loglevel=INFO

Task modules are registered via `include` as they are built:
  Chunk 4: app.workers.tasks (pipeline step execution)
  Chunk 5: verification tasks
  M8:      nightly learning-loop aggregation (Celery Beat schedule below)
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "leadpilot",
    broker=settings.broker_url,
    backend=settings.result_backend,
    include=[
        "app.workers.tasks",
        "app.workers.lead_tasks",
        "app.workers.outreach_tasks",
        # M8 additions
        "app.workers.learning_tasks",   # nightly aggregation + A/B promotion
        "app.workers.send_tasks",       # C4 send-time-aware sending
        "app.workers.webhook_tasks",    # C5 reliable outbound webhooks
        "app.workers.beat_heartbeat",   # C3 beat liveness key
        "app.workers.support_tasks",    # Feature 3 chat retention purge
    ],
)

# Queue routing.
#
# WITHOUT this block every task was published to Celery's implicit default
# queue, "celery". docker-compose.prod.yml starts its three workers bound to
# -Q pipeline / -Q outreach / -Q learning,default, and monitoring.get_celery_stats()
# reports depth for those same four names — so NOTHING consumed "celery" and
# nothing published to the four queues. In production every worker would idle
# on empty queues while all real work (strategy generation, outreach dispatch,
# reply polling, the learning loop and the beat heartbeat) piled up unconsumed.
# It only worked in dev because the dev worker is started without -Q, which
# makes it consume "celery" by chance.
#
# Every registered task must appear below, and every queue named below must be
# consumed by some worker in docker-compose*.yml. Adding a task without adding
# a route silently strands it in "celery" again.
celery_app.conf.task_routes = {
    # Strategy construction: the 72/144-step pipeline, verification, sourcing.
    "leadpilot.run_pipeline": {"queue": "pipeline"},
    "leadpilot.run_verification": {"queue": "pipeline"},
    "leadpilot.leads.*": {"queue": "pipeline"},
    # Outreach: dispatch, sending, reply polling.
    "leadpilot.outreach.*": {"queue": "outreach"},
    "app.workers.send_tasks.*": {"queue": "outreach"},
    # Nightly learning loop.
    "app.workers.learning_tasks.*": {"queue": "learning"},
    # Everything else: heartbeat, outbound webhooks, ping.
    "app.workers.beat_heartbeat.*": {"queue": "default"},
    "app.workers.webhook_tasks.*": {"queue": "default"},
    "app.workers.support_tasks.*": {"queue": "default"},
    "leadpilot.ping": {"queue": "default"},
}

celery_app.conf.update(
    # A task with no matching route lands here rather than in "celery", so a
    # newly added, unrouted task is still picked up by the learning/default
    # worker instead of vanishing.
    task_default_queue="default",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Pipeline steps persist their own state to research_steps before ack,
    # but late-ack + reject-on-worker-lost gives an extra safety net so a
    # killed worker never silently drops a step.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=settings.pipeline_step_timeout_seconds + 60,
    task_soft_time_limit=settings.pipeline_step_timeout_seconds,
)

# Celery Beat schedule — the 24/7 heartbeat of outreach (M3) + learning (M8).
from celery.schedules import crontab  # noqa: E402


def _aggregation_hour() -> int:
    """PLAYBOOK_AGGREGATION_UTC_HOUR (default 02:00 UTC / 07:00 PKT)."""
    try:
        from app.core.config import settings as m8_settings
        return int(getattr(m8_settings, "PLAYBOOK_AGGREGATION_UTC_HOUR", 2))
    except Exception:
        return 2


celery_app.conf.beat_schedule = {
    "dispatch-due-messages": {
        "task": "leadpilot.outreach.dispatch",
        "schedule": float(settings.dispatch_interval_seconds),
    },
    "poll-gmail-replies": {
        "task": "leadpilot.outreach.poll_replies",
        "schedule": float(settings.reply_poll_interval_seconds),
    },
    # M8-C1: nightly learning-loop aggregation
    "learning-loop-aggregation": {
        "task": "app.workers.learning_tasks.run_strategy_aggregation",
        "schedule": crontab(hour=_aggregation_hour(), minute=5),
    },
    # M8-C2: A/B / multi-variate auto-promotion sweep (30 min after aggregation)
    "ab-auto-promotion": {
        "task": "app.workers.learning_tasks.auto_promote_winners",
        "schedule": crontab(hour=_aggregation_hour(), minute=35),
    },
    # M8-C3: beat liveness heartbeat (60s, TTL 300s — health endpoint reads it)
    "beat-heartbeat": {
        "task": "app.workers.beat_heartbeat.refresh_celery_heartbeat",
        "schedule": 60.0,
    },
    # Feature 3: delete chat history past SUPPORT_CHAT_RETENTION_DAYS.
    # 03:20 UTC — after the learning-loop jobs at :05 and :35 so a slow
    # aggregation never delays the purge, and vice versa.
    "support-chat-retention-purge": {
        "task": "app.workers.support_tasks.purge_old_chats",
        "schedule": crontab(hour=3, minute=20),
    },
    # NOTE: outbound webhook retries (M8-C5) self-schedule via apply_async
    # countdown inside deliver_webhook — no beat sweep needed.
}
