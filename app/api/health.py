"""
Health and readiness endpoints.

GET /health                  — Public. DB + Redis + Celery heartbeat check.
                               Returns 200 for ok/degraded, 503 for down.
GET /health/learning-loop    — Admin only. Last nightly aggregation run status.
GET /health/channels         — Auth required. Per-channel integration health.

Celery health is detected via a Redis heartbeat key that the Celery Beat task
`beat_heartbeat.refresh_celery_heartbeat` updates every minute.
# TODO: verify this is the most reliable Celery health pattern for your deployment;
# alternatives include Flower API or celery.control.inspect().ping(), but the Redis
# key approach avoids Celery broker blocking on health-check requests.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.core.logging import get_logger
from app.api.deps import get_current_user, require_admin
from app.services.health_checks import (
    CELERY_HEARTBEAT_KEY,
    CELERY_HEARTBEAT_TTL_SECONDS,
    check_celery_heartbeat,
    check_database,
    check_redis,
)

logger = get_logger("api.health")
router = APIRouter(prefix="/health", tags=["health"])

# Re-exported for anything that imported them from here before the checks
# moved to app/services/health_checks.py.
__all__ = ["router", "CELERY_HEARTBEAT_KEY", "CELERY_HEARTBEAT_TTL_SECONDS"]


# ---------------------------------------------------------------------------
# GET /health  — public
# ---------------------------------------------------------------------------

@router.get("")
async def health_check(
    db: Session = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict[str, Any]:
    """
    Public health check. Used by:
    - docker-compose healthcheck
    - Railway/Render health probe
    - `clienthunter serve` startup wait loop

    Returns HTTP 200 with {"status": "ok"} when all components are healthy.
    Returns HTTP 200 with {"status": "degraded"} when non-critical components are down.
    Returns HTTP 503 with {"status": "down"} when DB or Redis is unreachable.
    """
    components: dict[str, dict[str, Any]] = {}
    overall = "ok"

    # The checks live in app/services/health_checks.py, shared with
    # GET /status/public. This function only composes them, exactly as it did
    # when they were inline (response bytes pinned by
    # tests/test_status_public.py::TestHealthUnchanged).

    # --- Database ---
    components["database"] = check_database(db)
    if components["database"]["status"] == "down":
        overall = "down"

    # --- Redis ---
    components["redis"] = await check_redis(redis)
    if components["redis"]["status"] == "down":
        overall = "down"

    # --- Celery workers (via heartbeat key) ---
    components["celery"] = await check_celery_heartbeat(redis)
    if components["celery"]["status"] != "ok" and overall == "ok":
        overall = "degraded"

    response_body: dict[str, Any] = {"status": overall, "components": components}
    status_code = 503 if overall == "down" else 200

    if status_code == 503:
        raise HTTPException(status_code=503, detail=response_body)
    return response_body


# ---------------------------------------------------------------------------
# GET /health/learning-loop  — admin only
# ---------------------------------------------------------------------------

@router.get("/learning-loop")
async def learning_loop_health(
    redis: aioredis.Redis = Depends(get_redis),
    current_user=Depends(require_admin),
) -> dict[str, Any]:
    """
    Admin-only. Returns the status of the nightly learning-loop aggregation job.
    Surfaces silent failures without requiring log access.
    """
    try:
        last_run_raw = await redis.get("learning_loop:last_run")
        last_duration_raw = await redis.get("learning_loop:last_duration_ms")
        patterns_updated_raw = await redis.get("learning_loop:patterns_updated")
        last_error_raw = await redis.get("learning_loop:last_error")

        last_run = float(last_run_raw) if last_run_raw else None
        last_run_ago_seconds = int(time.time() - last_run) if last_run else None

        return {
            "status": "ok" if last_error_raw is None else "error",
            "last_run_at": last_run,
            "last_run_seconds_ago": last_run_ago_seconds,
            "last_run_duration_ms": int(last_duration_raw) if last_duration_raw else None,
            "patterns_updated_last_run": int(patterns_updated_raw) if patterns_updated_raw else None,
            # The stored value is the worker's raw exception text; the
            # details are in /admin/task-errors and the log. A response
            # carries a fixed sentence (gaps-sweep-2 #17).
            "last_error": "the last run failed" if last_error_raw else None,
            "recommendation": (
                "Check /admin/task-errors for details."
                if last_error_raw else
                ("No aggregation has run yet — confirm Celery Beat is scheduled."
                 if last_run is None else None)
            ),
        }
    except Exception as e:
        # Fixed text even for admins: exception text from the Redis client can
        # name hosts and ports, and the log already has it.
        logger.error("health.learning_loop_check_failed", error=str(e),
                     error_type=type(e).__name__)
        return {"status": "unknown", "error": "check failed"}


# ---------------------------------------------------------------------------
# GET /health/channels  — auth required
# ---------------------------------------------------------------------------

def _channel_check_failed(channel: str, exc: Exception) -> dict[str, Any]:
    """A channel check that raised: a fixed message for the caller, the
    exception in the log. Exception text from the Redis client can name hosts
    and ports, which no API response should carry."""
    logger.error("health.channel_check_failed", channel=channel, error=str(exc),
                 error_type=type(exc).__name__)
    return {"status": "unknown", "error": "check failed"}


@router.get("/channels")
async def channel_health(
    db: Session = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    current_user=Depends(get_current_user),
) -> dict[str, Any]:
    """
    Auth required. Per-channel integration health. Tells the user why a
    campaign looks stuck without needing to dig through logs.
    """
    user_id = str(current_user.id)
    channels: dict[str, Any] = {}

    # --- Gmail ---
    try:
        gmail_token_key = f"gmail:token_valid:{user_id}"
        gmail_quota_key = f"gmail:quota_remaining:{user_id}"
        token_valid = await redis.get(gmail_token_key)
        quota_remaining = await redis.get(gmail_quota_key)
        channels["gmail"] = {
            "status": "ok" if token_valid == "1" else "needs_reauth",
            "oauth_token_valid": token_valid == "1",
            "daily_quota_remaining": int(quota_remaining) if quota_remaining else None,
            "action_required": None if token_valid == "1" else "Re-authenticate Gmail at /integrations/gmail/auth-url",
        }
    except Exception as e:
        channels["gmail"] = _channel_check_failed("gmail", e)

    # --- WhatsApp ---
    try:
        wa_token_expiry_key = f"whatsapp:token_expiry:{user_id}"
        wa_last_event_key = "whatsapp:last_webhook_event"
        token_expiry_raw = await redis.get(wa_token_expiry_key)
        last_event_raw = await redis.get(wa_last_event_key)

        token_expires_at = float(token_expiry_raw) if token_expiry_raw else None
        token_valid = token_expires_at is not None and token_expires_at > time.time()
        last_event_seconds_ago = (
            int(time.time() - float(last_event_raw)) if last_event_raw else None
        )

        channels["whatsapp"] = {
            "status": "ok" if token_valid else "token_expired",
            "token_valid": token_valid,
            "token_expires_at": token_expires_at,
            "last_webhook_event_seconds_ago": last_event_seconds_ago,
            "webhook_reachable": last_event_seconds_ago is not None and last_event_seconds_ago < 86400,
            "action_required": None if token_valid else "Refresh WhatsApp access token in Meta Business console",
        }
    except Exception as e:
        channels["whatsapp"] = _channel_check_failed("whatsapp", e)

    # --- Calendly ---
    try:
        cal_last_event_key = "calendly:last_webhook_event"
        cal_last_raw = await redis.get(cal_last_event_key)
        last_cal_seconds_ago = (
            int(time.time() - float(cal_last_raw)) if cal_last_raw else None
        )
        channels["calendly"] = {
            "status": "ok",
            "last_webhook_event_seconds_ago": last_cal_seconds_ago,
            "webhook_configured": last_cal_seconds_ago is not None,
            "action_required": (
                None if last_cal_seconds_ago is not None
                else "Configure Calendly webhook at /integrations/calendly/setup"
            ),
        }
    except Exception as e:
        channels["calendly"] = _channel_check_failed("calendly", e)

    overall = "ok"
    for ch_data in channels.values():
        if ch_data.get("status") not in ("ok", "unknown"):
            overall = "degraded"
            break

    return {"status": overall, "channels": channels}
