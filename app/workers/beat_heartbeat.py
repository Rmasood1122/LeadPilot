"""
Celery Beat heartbeat task.

Writes the current UNIX timestamp to the Redis key `celery:heartbeat` every 60 seconds.
The /health endpoint reads this key to determine if Celery Beat (and by extension,
any workers processing Beat-scheduled tasks) is alive.

Register in your Celery Beat schedule:
    CELERY_BEAT_SCHEDULE = {
        ...
        "celery-heartbeat": {
            "task": "app.workers.beat_heartbeat.refresh_celery_heartbeat",
            "schedule": 60.0,  # every 60 seconds
        },
        ...
    }
"""
from __future__ import annotations

import time

from app.workers.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger("workers.beat_heartbeat")

HEARTBEAT_KEY = "celery:heartbeat"
HEARTBEAT_KEY_TTL = 300  # seconds — expire if Beat stops running


@celery_app.task(name="app.workers.beat_heartbeat.refresh_celery_heartbeat", bind=True)
def refresh_celery_heartbeat(self) -> dict:
    """
    Minute-interval task that proves Celery Beat is scheduling tasks
    and at least one worker is processing them.
    """
    try:
        from app.core.redis_client import get_sync_redis
        redis = get_sync_redis()
        ts = time.time()
        redis.set(HEARTBEAT_KEY, str(ts), ex=HEARTBEAT_KEY_TTL)
        logger.debug("celery_heartbeat_refreshed", timestamp=ts)
        return {"status": "ok", "timestamp": ts}
    except Exception as e:
        logger.error("celery_heartbeat_failed", error=str(e))
        raise
