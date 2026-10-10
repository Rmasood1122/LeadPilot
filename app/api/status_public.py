"""GET /status/public — component status for status.calendarharvest.com.

PUBLIC, unauthenticated, read-only. The status site (status-page/, a separate
Vercel project) fetches this server-side every 60 s, alongside UptimeRobot's
external probes. Design and the founders' setup steps:
docs/program/STATUS_PAGE.md.

WHAT IT MAY SAY
Per component: a stable id, a customer-facing name, one of
operational | degraded | partial_outage | major_outage | maintenance, and
when it was checked. Nothing else: no error strings, hostnames, queue names,
counts, timings or tenant data. The internal check results
(app/services/health_checks.py, the same checks GET /health runs) carry
exception text and ages; this module maps them to the vocabulary above and
forwards none of their strings. tests/test_status_public.py asserts the exact
key set and value set of every response.

WHAT IT MEASURES (only what something actually checks)
  api                    DB `SELECT 1` and Redis PING
                           both ok -> operational
                           DB ok, Redis down -> partial_outage (reads work;
                             queueing work, caching and rate limiting do not)
                           DB down -> major_outage
  background-processing  Celery beat heartbeat age (written every 60 s by a
                         beat-scheduled task, so it needs beat AND a worker)
                           fresh (<= 120 s) -> operational
                           stale (120-300 s; the key's TTL is 300 s) -> degraded
                           missing, unreadable, or Redis down -> major_outage
                             (nothing proves work is being processed, and the
                             broker shares that Redis in production)
  ai-features            Anthropic Models API with the gateway's key: free, no
                         model call (health_checks.check_ai_gateway documents
                         the mapping and its blind spots)
  booking-pages          DB reachable and the three booking tables queryable
                           ok -> operational, else major_outage
"Website & app" is NOT here: it is the static Vercel frontend, which this API
cannot observe. The status site takes it from UptimeRobot alone.
`maintenance` is part of the contract but nothing in the backend emits it;
the status site sets it from an incident file whose impact is maintenance.

COST AND ABUSE
The assembled body is cached in-process for RESPONSE_TTL_SECONDS (30 s), so a
burst costs at most one set of checks per process per 30 s; the AI probe has
its own 5-minute cache. enforce_rate_limit is the handler's first statement
(RATE_LIMIT_PUBLIC_STATUS per client IP per hour), the same pattern as the
other public routes (/public/roi, /audit/verify).

CORS is deliberately not widened for this route: the status site calls it from
its server, never from a browser.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.rate_limiting import client_ip, enforce_rate_limit
from app.core.redis_client import get_redis
from app.db.base import get_db
from app.services import health_checks

router = APIRouter(prefix="/status", tags=["status"])

OPERATIONAL = "operational"
DEGRADED = "degraded"
PARTIAL_OUTAGE = "partial_outage"
MAJOR_OUTAGE = "major_outage"
MAINTENANCE = "maintenance"
PUBLIC_STATUSES = (OPERATIONAL, DEGRADED, PARTIAL_OUTAGE, MAJOR_OUTAGE, MAINTENANCE)

# (id, customer-facing name). The ids are a contract with status-page/ —
# renaming one is a coordinated change in both places.
COMPONENTS: tuple[tuple[str, str], ...] = (
    ("api", "API"),
    ("background-processing", "Background processing"),
    ("ai-features", "AI features"),
    ("booking-pages", "Booking pages"),
)

RESPONSE_TTL_SECONDS = 30
_PUBLIC_HEADERS = {"Cache-Control": f"public, max-age={RESPONSE_TTL_SECONDS}"}

_cache: dict[str, Any] = {"at": None, "body": None}


def reset_cache() -> None:
    _cache["at"] = None
    _cache["body"] = None


# ---------------------------------------------------------------------------
# Internal result -> public status. Pure functions; only the `status` field
# and the presence of an age are read, never a message.
# ---------------------------------------------------------------------------

def api_status(database: dict, redis: dict) -> str:
    if database.get("status") != "ok":
        return MAJOR_OUTAGE
    if redis.get("status") != "ok":
        return PARTIAL_OUTAGE
    return OPERATIONAL


def background_status(redis: dict, celery: dict) -> str:
    if redis.get("status") != "ok":
        return MAJOR_OUTAGE
    if celery.get("status") == "ok":
        return OPERATIONAL
    if "last_beat_seconds_ago" in celery:  # stale but present
        return DEGRADED
    return MAJOR_OUTAGE  # missing or unreadable


def ai_status(ai: dict) -> str:
    return {"ok": OPERATIONAL, "degraded": DEGRADED}.get(ai.get("status"), MAJOR_OUTAGE)


def booking_status(database: dict, booking: dict | None) -> str:
    if database.get("status") != "ok" or booking is None:
        return MAJOR_OUTAGE
    return OPERATIONAL if booking.get("status") == "ok" else MAJOR_OUTAGE


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


async def build_public_status(db, redis) -> dict[str, Any]:
    """Run the checks once and return the public body (uncached)."""
    database = health_checks.check_database(db)
    redis_result = await health_checks.check_redis(redis)
    celery = await health_checks.check_celery_heartbeat(redis)
    ai = await health_checks.check_ai_gateway()
    booking = health_checks.check_booking_tables(db) if database.get("status") == "ok" else None

    checked_at = _utc_now_iso()
    statuses = {
        "api": api_status(database, redis_result),
        "background-processing": background_status(redis_result, celery),
        "ai-features": ai_status(ai),
        "booking-pages": booking_status(database, booking),
    }
    return {
        "components": [
            {"id": cid, "name": name, "status": statuses[cid], "checked_at": checked_at}
            for cid, name in COMPONENTS
        ]
    }


@router.get("/public")
async def public_status(
    request: Request,
    db: Session = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> JSONResponse:
    """PUBLIC — no auth. Component status for the status page (30 s cache)."""
    enforce_rate_limit(f"ip:{client_ip(request)}", "public_status", "RATE_LIMIT_PUBLIC_STATUS")
    now = time.monotonic()
    if _cache["body"] is not None and now - _cache["at"] < RESPONSE_TTL_SECONDS:
        return JSONResponse(content=_cache["body"], headers=_PUBLIC_HEADERS)
    body = await build_public_status(db, redis)
    _cache["at"], _cache["body"] = now, body
    return JSONResponse(content=body, headers=_PUBLIC_HEADERS)
