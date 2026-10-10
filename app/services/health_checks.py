"""Health checks shared by GET /health and GET /status/public.

Extracted from app/api/health.py (Phase 3, status.calendarharvest.com) so the
public status endpoint is built from the SAME checks as /health instead of a
copy that could drift. Each function returns exactly the component dict
/health has always returned -- tests/test_status_public.py::TestHealthUnchanged
pins /health's response bytes, and was run against the pre-extraction code.

These dicts are INTERNAL. They carry exception text (`error`) and timings,
which /health has always exposed and /status/public must not. The mapping to
the public vocabulary lives in app/api/status_public.py and never forwards a
string from here.

check_ai_gateway() is new and used only by /status/public; /health does not
call it, so /health's behaviour and cost are unchanged.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from sqlalchemy import text

from app.core.logging import get_logger

# Same logger name and event names /health always used, so existing log
# searches ("health.database_unreachable", ...) keep matching.
logger = get_logger("api.health")

# Celery heartbeat key written by app/workers/beat_heartbeat.py every 60 seconds
CELERY_HEARTBEAT_KEY = "celery:heartbeat"
CELERY_HEARTBEAT_TTL_SECONDS = 120  # if key is older than 2 minutes, workers are stale


def check_database(db) -> dict[str, Any]:
    """`SELECT 1` on the request's session. {"status": "ok"} or "down"."""
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error("health.database_unreachable", error=str(e))
        return {"status": "down", "error": "connection failed"}


async def check_redis(redis) -> dict[str, Any]:
    """PING on the async client. {"status": "ok"} or "down"."""
    try:
        await redis.ping()
        return {"status": "ok"}
    except Exception as e:
        logger.error("health.redis_unreachable", error=str(e))
        return {"status": "down", "error": "ping failed"}


async def check_celery_heartbeat(redis) -> dict[str, Any]:
    """Age of the beat heartbeat key. "ok" when fresher than
    CELERY_HEARTBEAT_TTL_SECONDS, otherwise "degraded".

    Shapes (all pinned by tests):
      fresh   {"status": "ok", "last_beat_seconds_ago": N}
      stale   {"status": "degraded", "reason": "heartbeat stale (Ns ago)", "last_beat_seconds_ago": N}
      missing {"status": "degraded", "reason": "no heartbeat key found"}
      error   {"status": "degraded", "error": "<exception text>"}
    The writer sets the key with a 300 s TTL (beat_heartbeat.HEARTBEAT_KEY_TTL),
    so "stale" can only ever cover ages between 120 s and 300 s; older than
    that the key is gone and the result is "missing".
    """
    try:
        heartbeat_raw = await redis.get(CELERY_HEARTBEAT_KEY)
        if heartbeat_raw is None:
            # No heartbeat key — either workers never started or key expired
            return {"status": "degraded", "reason": "no heartbeat key found"}
        last_beat = float(heartbeat_raw)
        age_seconds = time.time() - last_beat
        if age_seconds > CELERY_HEARTBEAT_TTL_SECONDS:
            return {
                "status": "degraded",
                "reason": f"heartbeat stale ({int(age_seconds)}s ago)",
                "last_beat_seconds_ago": int(age_seconds),
            }
        return {
            "status": "ok",
            "last_beat_seconds_ago": int(age_seconds),
        }
    except Exception as e:
        logger.error("health.celery_check_failed", error=str(e))
        return {"status": "degraded", "error": str(e)}


# ---------------------------------------------------------------------------
# AI gateway reachability (used by /status/public only)
# ---------------------------------------------------------------------------
#
# THE CHECK, AND WHY IT IS THIS ONE
# "Are AI features working?" without paying for a model call per probe.
# GET https://api.anthropic.com/v1/models?limit=1 is the Models API: it bills
# no tokens, it is authenticated with the same key the gateway
# (app/services/anthropic_client.py) uses, and it travels the same network
# path. So one call answers both "is the key accepted?" and "can this process
# reach Anthropic?".
#
#   no ANTHROPIC_API_KEY configured        -> down      (every model call fails)
#   200                                    -> ok
#   401 / 403 / 404                        -> down      (key revoked, no access)
#   429 / 5xx / 529 / timeout / network    -> degraded  (the same classes the
#                                             gateway retries: expected to recover)
#   anything else                          -> degraded
#
# WHAT IT DOES NOT SEE (documented in docs/program/STATUS_PAGE.md):
#   * an exhausted credit balance -- the Models API does not consume credit, so
#     it answers 200 while every Messages call returns 400. That surfaces in
#     the pipeline's terminal-failure path, not here.
#   * a wrong ANTHROPIC_MODEL name -- also only visible on a Messages call.
#
# The result is cached in-process for AI_PROBE_TTL_SECONDS, keyed on a hash of
# the key (so rotating the key re-probes at once), which caps the probe at
# ~288 free requests per day per API process however often the status
# endpoint is hit. The 30 s response cache in status_public sits in front of
# this as well.

ANTHROPIC_MODELS_URL = "https://api.anthropic.com/v1/models"
ANTHROPIC_VERSION_HEADER = "2023-06-01"
AI_PROBE_TIMEOUT_SECONDS = 5.0
AI_PROBE_TTL_SECONDS = 300

_ai_probe_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def reset_ai_probe_cache() -> None:
    _ai_probe_cache.clear()


async def _probe_models_endpoint(api_key: str) -> dict[str, Any]:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=AI_PROBE_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                ANTHROPIC_MODELS_URL,
                params={"limit": 1},
                headers={"x-api-key": api_key,
                         "anthropic-version": ANTHROPIC_VERSION_HEADER},
            )
    except Exception as e:  # timeout, DNS, refused, TLS
        logger.warning("health.ai_gateway_unreachable", error=type(e).__name__)
        return {"status": "degraded", "reason": "unreachable"}
    code = resp.status_code
    if code == 200:
        return {"status": "ok"}
    if code in (401, 403, 404):
        logger.error("health.ai_gateway_rejected", http_status=code)
        return {"status": "down", "reason": f"http {code}"}
    logger.warning("health.ai_gateway_unhealthy", http_status=code)
    return {"status": "degraded", "reason": f"http {code}"}


async def check_ai_gateway(api_key: str | None = None, *, probe=None) -> dict[str, Any]:
    """Reachability of the Anthropic gateway with no billed model call.

    `api_key` defaults to the gateway's own setting. `probe` is injectable for
    tests: an async callable taking the key and returning the result dict.
    """
    if api_key is None:
        from app.config import settings

        api_key = settings.anthropic_api_key
    api_key = (api_key or "").strip()
    if not api_key:
        return {"status": "down", "reason": "no api key configured"}

    cache_key = hashlib.sha256(api_key.encode()).hexdigest()
    now = time.monotonic()
    cached = _ai_probe_cache.get(cache_key)
    if cached is not None and now - cached[0] < AI_PROBE_TTL_SECONDS:
        return cached[1]

    result = await (probe or _probe_models_endpoint)(api_key)
    _ai_probe_cache.clear()  # one key at a time; drop results for an old key
    _ai_probe_cache[cache_key] = (now, result)
    return result


# ---------------------------------------------------------------------------
# Booking pages (used by /status/public only)
# ---------------------------------------------------------------------------

def check_booking_tables(db) -> dict[str, Any]:
    """Can the public booking flow read and write its three tables?

    The public booking page (frontend /book/) needs exactly these: the page
    row, the owner's availability, and existing bookings (slot computation and
    the UNIQUE-backed write). It needs no Redis -- its limiter fails open --
    and no third-party API. Each statement selects the literal 1, so no
    tenant row is read into this process.
    """
    from sqlalchemy import literal, select

    from app.db.models import CalendarAvailability, CalendarBooking, CalendarBookingPage

    try:
        for model in (CalendarBookingPage, CalendarAvailability, CalendarBooking):
            db.execute(select(literal(1)).select_from(model).limit(1))
        return {"status": "ok"}
    except Exception as e:
        logger.error("health.booking_tables_unreachable", error=type(e).__name__)
        try:
            db.rollback()  # leave the session usable for the caller
        except Exception:
            pass
        return {"status": "down"}
