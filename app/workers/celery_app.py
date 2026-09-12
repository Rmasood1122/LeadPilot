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
        # Engagement Hub: post-booking work, meeting summaries, stale-meeting
        # sweep. The follow-up tasks live in outreach_tasks (already included
        # above) because they send outreach messages and belong on the same
        # queue as every other send.
        "app.workers.calendar_tasks",
        # Feature expansion: the notification hub's queue, and the meeting
        # prep brief + pre-meeting reminders that feed it.
        "app.workers.notification_tasks",
        "app.workers.meeting_prep_tasks",
        # Feature Group 3: send-time windows + weekly reply sentiment.
        "app.workers.analytics_tasks",
        # Feature Group 4: HubSpot / Salesforce two-way sync.
        "app.workers.crm_tasks",
        # Feature Group 9: daily sending-domain health + blacklist sweep.
        "app.workers.deliverability_tasks",
        # Feature Group 1: idle-campaign mutation sweep, lead rescoring,
        # market-signal refresh.
        "app.workers.intelligence_tasks",
        # Feature Group 6: AI call transcript analysis.
        "app.workers.call_tasks",
        # Tool integrations: AegisAudit draft audit, PostIQ drafts,
        # SIGNALFORGE lead research.
        "app.workers.tool_integration_tasks",
        # Feature 1: six-hourly pipeline health score.
        "app.workers.health_tasks",
        # Feature 2: reply intelligence (category + next action + draft).
        "app.workers.reply_tasks",
        # Feature 3: founder voice cloning from LinkedIn posts.
        "app.workers.voice_tasks",
        # Feature 4: twelve-hourly competitor displacement sweep.
        "app.workers.displacement_tasks",
        # Feature 5: nightly client ROI snapshots.
        "app.workers.roi_tasks",
        # Website builder: page generation + static export (on demand only).
        "app.workers.site_tasks",
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
    # Engagement Hub. "default" rather than "outreach": these tasks send
    # transactional email and write CRM rows, they do not dispatch outreach,
    # and the outreach worker's concurrency is sized for send throughput
    # against a daily cap. Note the follow-up tasks are NOT here -- they match
    # leadpilot.outreach.* above, which is correct: they send real outbound
    # messages under the same caps and windows as any other send.
    "app.workers.calendar_tasks.*": {"queue": "default"},
    "leadpilot.ping": {"queue": "default"},
    # Feature expansion: the `notifications` queue. Push/Slack/webhook fan-out
    # and the meeting prep brief are user-facing and time-sensitive -- a
    # one-hour reminder that queues behind a 144-step pipeline or the nightly
    # learning loop arrives after the call has started. Its own queue gets its
    # own worker (docker-compose.prod.yml: celery-worker-notifications).
    "app.workers.notification_tasks.*": {"queue": "notifications"},
    "app.workers.meeting_prep_tasks.*": {"queue": "notifications"},
    # Feature Group 1. The mutation sweep is the learning loop reacting to
    # outcomes, so it runs with it; rescoring and signal refresh are batched
    # model/API work shaped like sourcing, so they run with it. The exact name
    # is matched before the glob.
    "app.workers.intelligence_tasks.check_idle_campaigns": {"queue": "learning"},
    "app.workers.intelligence_tasks.*": {"queue": "pipeline"},
    # Feature Group 6: the phone channel's reply routing -- same queue as
    # every other reply path.
    "app.workers.call_tasks.*": {"queue": "outreach"},
    # Feature Group 3: the learning loop reacting to opens and replies.
    "app.workers.analytics_tasks.*": {"queue": "learning"},
    # Feature Group 4: CRM sync is one user's integration I/O at a time --
    # neither outreach volume nor the learning loop -- like webhook delivery.
    "app.workers.crm_tasks.*": {"queue": "default"},
    # Feature Group 9: outbound DNS / API lookups, one user at a time.
    "app.workers.deliverability_tasks.*": {"queue": "default"},
    # Tool integrations: one outbound call to an internal/partner service at
    # a time -- integration I/O like CRM sync and webhook delivery.
    "tool_integrations.*": {"queue": "default"},
    # Feature 1: the pipeline health sweep is aggregation over outcomes,
    # enrollments and leads -- the same shape of work as the learning loop,
    # and never time-critical to the minute.
    "app.workers.health_tasks.*": {"queue": "learning"},
    # Feature 2: classifying an inbound reply is the reply path, same as
    # leadpilot.outreach.poll_replies and call_tasks above.
    "app.workers.reply_tasks.*": {"queue": "outreach"},
    # Feature 3: one user-triggered model call with a human watching for the
    # result. NOT `pipeline` -- that queue runs 72/144-step strategy builds at
    # concurrency 2, and a voice analysis behind one would take minutes.
    "app.workers.voice_tasks.*": {"queue": "default"},
    # Feature 4: batched external-API-plus-model work over every lead's posts
    # -- the same shape as intelligence_tasks' rescoring, and it must not sit
    # in front of a time-sensitive send or a meeting reminder.
    "app.workers.displacement_tasks.*": {"queue": "pipeline"},
    # Feature 5: nightly aggregation, with the other nightly aggregations.
    "app.workers.roi_tasks.*": {"queue": "learning"},
    # Website builder. A page is the largest single generation in this system
    # (up to 8k output tokens of HTML), so it belongs with the other long
    # model calls and must not sit in front of a time-sensitive send. Note
    # the task names are "workers.site_tasks.*", not "app.workers.site_tasks.*"
    # -- they are registered under an explicit short name.
    "workers.site_tasks.*": {"queue": "pipeline"},
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
    # Engagement Hub, Feature 1: the automated follow-up sweep. Every 30
    # minutes by default (FOLLOWUP_SWEEP_INTERVAL_SECONDS). It only ENQUEUES;
    # each send goes through the same compliance path as any other message.
    "check-followup-due": {
        "task": "leadpilot.outreach.check_followup_due",
        "schedule": float(settings.followup_sweep_interval_seconds),
    },
    # Engagement Hub, Feature 3: close meetings nobody pressed End on. Hourly
    # rather than on a schedule tied to meeting times, because the thing being
    # cleaned up is precisely the case where nobody was watching. A meeting
    # left in_progress keeps blocking calendar slots and keeps its lead's
    # enrollment paused, so this is not cosmetic.
    "close-stale-meetings": {
        "task": "app.workers.calendar_tasks.close_stale_meetings",
        "schedule": 3600.0,
    },
    # Feature Group 7: 24h and 1h pre-meeting reminders. Every five minutes;
    # each reminder is claimed with a conditional UPDATE, so overlapping
    # sweeps cannot double-send (see meeting_prep_tasks).
    "send-meeting-reminders": {
        "task": "app.workers.meeting_prep_tasks.send_meeting_reminders",
        "schedule": float(settings.meeting_reminder_sweep_seconds),
    },
    # Feature Group 1: mutate campaigns idle for N days with zero replies.
    # Daily, after the learning-loop aggregation (:05) and promotion (:35) so
    # it reasons from that night's numbers.
    "check-idle-campaigns": {
        "task": "app.workers.intelligence_tasks.check_idle_campaigns",
        "schedule": crontab(hour=_aggregation_hour(), minute=50),
    },
    # Feature Group 3: recompute every campaign's smart-send windows after
    # the aggregation, and roll up last week's reply sentiment (Mondays) --
    # the objection-spike alert runs off that roll-up.
    "refresh-send-windows": {
        "task": "app.workers.analytics_tasks.refresh_send_windows",
        "schedule": crontab(hour=_aggregation_hour(), minute=15),
    },
    "aggregate-reply-sentiment": {
        "task": "app.workers.analytics_tasks.aggregate_reply_sentiment",
        "schedule": crontab(day_of_week=1, hour=_aggregation_hour(), minute=25),
    },
    # Feature Group 4: push what changed to each connected CRM and pull its
    # linked records back. Catches every status change no event announces.
    "crm-sync": {
        "task": "app.workers.crm_tasks.sync_all",
        "schedule": 900.0,
    },
    # Feature Group 9: daily blacklist + health check of every sending
    # domain. A new listing pauses the user's campaigns immediately.
    "deliverability-checks": {
        "task": "app.workers.deliverability_tasks.run_daily_checks",
        "schedule": crontab(hour=6, minute=10),
    },
    # Feature 1: recompute every campaign's pipeline health score. Every six
    # hours, at :40 past the hour, so it never starts in the same minute as
    # the learning-loop jobs (:05/:15/:25/:35/:50) that share this queue.
    "refresh-pipeline-health": {
        "task": "app.workers.health_tasks.refresh_all_pipeline_health",
        "schedule": crontab(hour="*/6", minute=40),
    },
    # Feature 4: competitor displacement sweep. Every twelve hours at :20 --
    # offset from the health sweep (:40) and the learning-loop hour so the
    # three never contend for the same worker minute.
    "scan-displacement-signals": {
        "task": "app.workers.displacement_tasks.scan_all_strategies",
        "schedule": crontab(hour="*/12", minute=20),
    },
    # Feature 5: the client ROI snapshot, daily at 01:00 UTC. Late enough
    # that yesterday has closed everywhere the product sells (US -> NZ), and
    # finished before the 02:00 learning-loop aggregation wants the same
    # worker.
    "refresh-roi-snapshots": {
        "task": "app.workers.roi_tasks.refresh_all_roi_snapshots",
        "schedule": crontab(hour=1, minute=0),
    },
    # NOTE: outbound webhook retries (M8-C5) self-schedule via apply_async
    # countdown inside deliver_webhook — no beat sweep needed.
}
