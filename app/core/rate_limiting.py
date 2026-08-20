"""
Per-user, per-endpoint rate limiting via Redis sliding-window counters.

Usage:
    from app.core.rate_limiting import rate_limit

    @router.post("/products/{id}/strategies")
    @rate_limit(max_calls=10, window_seconds=3600)
    async def create_strategy(...):
        ...

On limit exceeded: HTTP 429 with Retry-After header + structured body:
    {"error": "rate_limit_exceeded", "retry_after": N, "limit": 10, "window": 3600}

Keys: rate:{user_id}:{endpoint_slug}
TTL: window_seconds (auto-expire after window)

Global kill-switch endpoints (admin only):
    GET  /admin/rate-limits/{user_id}    — current counters
    POST /admin/rate-limits/reset/{user_id} — clear all counters for user
"""
from __future__ import annotations

import functools
import time
from typing import Callable, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger("core.rate_limiting")


def _endpoint_slug(endpoint_name: str) -> str:
    """Convert an endpoint function name to a Redis-safe slug."""
    return endpoint_name.lower().replace(" ", "_").replace("/", "_")[:64]


def _rl_key(user_id: str, slug: str) -> str:
    return f"rate:{user_id}:{slug}"


def _get_counter(redis, key: str, window_seconds: int) -> tuple[int, int]:
    """
    Sliding window via Redis INCR + EXPIRE.
    Returns (current_count, ttl_remaining_seconds).
    """
    pipe = redis.pipeline()
    pipe.incr(key)
    pipe.ttl(key)
    results = pipe.execute()
    count = results[0]
    ttl = results[1]

    # First call (count==1) or expired key (ttl==-1): set the window TTL
    if ttl < 0:
        redis.expire(key, window_seconds)
        ttl = window_seconds

    return count, ttl


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int, limit: int, window: int):
        self.retry_after = retry_after
        self.limit = limit
        self.window = window


def rate_limit(
    max_calls: int,
    window_seconds: int,
    per: str = "user",           # "user" only for now; "ip" could be added
    scope: Optional[str] = None,  # override the slug (default: decorated function name)
):
    """
    Decorator for FastAPI route handlers.
    Must be applied AFTER @router.X() because FastAPI resolves dependencies top-down.

    The decorated function must have `request: Request` in its signature
    (standard for FastAPI endpoints) or use `Depends(get_current_user)`.
    """
    def decorator(func: Callable) -> Callable:
        slug = scope or _endpoint_slug(func.__name__)

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            request: Optional[Request] = kwargs.get("request") or next(
                (a for a in args if isinstance(a, Request)), None
            )
            current_user = kwargs.get("current_user")

            user_id = "anonymous"
            if current_user and hasattr(current_user, "id"):
                user_id = str(current_user.id)

            try:
                from app.core.redis_client import get_sync_redis
                redis = get_sync_redis()
                key = _rl_key(user_id, slug)
                count, ttl = _get_counter(redis, key, window_seconds)

                if count > max_calls:
                    logger.warning(
                        "rate_limit.exceeded",
                        user_id=user_id,
                        endpoint=slug,
                        count=count,
                        limit=max_calls,
                    )
                    raise RateLimitExceeded(
                        retry_after=max(ttl, 1),
                        limit=max_calls,
                        window=window_seconds,
                    )
            except RateLimitExceeded:
                raise
            except Exception as e:
                # Redis failure: fail open (log but allow the request)
                logger.warning("rate_limit.redis_error", error=str(e), endpoint=slug)

            return await func(*args, **kwargs)

        return wrapper
    return decorator


async def check_rate_limit(
    request: Request,
    user_id: str,
    endpoint_slug: str,
    max_calls: int,
    window_seconds: int,
) -> None:
    """
    Dependency-style rate-limit check (alternative to decorator).
    Raises HTTPException 429 on limit exceeded.
    """
    try:
        from app.core.redis_client import get_sync_redis
        redis = get_sync_redis()
        key = _rl_key(user_id, endpoint_slug)
        count, ttl = _get_counter(redis, key, window_seconds)

        if count > max_calls:
            logger.warning(
                "rate_limit.exceeded",
                user_id=user_id,
                endpoint=endpoint_slug,
                count=count,
            )
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "retry_after": max(ttl, 1),
                    "limit": max_calls,
                    "window": window_seconds,
                },
                headers={"Retry-After": str(max(ttl, 1))},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("rate_limit.check_failed", error=str(e))


def rate_limit_dependency(scope: str, setting_name: str,
                          window_seconds: int = 3600):
    """FastAPI dependency factory — the ONLY working way to apply a limit here.

    Use this, not the `rate_limit` decorator above. The decorator cannot be
    applied to this codebase's routes at all: its wrapper is `async def` and
    `await`s the endpoint, while every route that needs limiting
    (`create_strategy`, `source_leads_for_strategy`, ...) is a sync `def`.
    It also raises `RateLimitExceeded`, which has no exception handler
    registered, so it would surface as a 500 rather than a 429. Between those
    two problems the decorator was never applied to a single route, and every
    RATE_LIMIT_* setting was inert — verified live on 2026-08-20 by issuing six
    consecutive POST /products/{id}/strategies calls against a limit of 2 and
    receiving six 202s.

    A dependency works on sync and async endpoints alike, and `check_rate_limit`
    raises a proper HTTPException(429) with a Retry-After header.

    The limit is read from settings at REQUEST time, not import time, so
    changing the env var takes effect on restart without re-decorating.
    """
    async def _dependency(request: Request, current_user=Depends(_current_user_dep())):
        from app.core.config import settings as _settings

        max_calls = getattr(_settings, setting_name, None)
        if not max_calls or max_calls <= 0:
            return  # unset or explicitly disabled
        await check_rate_limit(
            request=request,
            user_id=str(getattr(current_user, "id", "anonymous")),
            endpoint_slug=scope,
            max_calls=int(max_calls),
            window_seconds=window_seconds,
        )

    return _dependency


# Auth endpoints are unauthenticated, so they key on the caller's IP (and, for
# login, the targeted account) rather than a user id. 15 minutes matches the
# documented RATE_LIMIT_AUTH window in app/core/config.py.
AUTH_WINDOW_SECONDS = 900


def client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limit keying.

    uvicorn is started with `--proxy-headers --forwarded-allow-ips='*'` in
    railway/api.json and docker-compose.prod.yml, so ProxyHeadersMiddleware has
    already rewritten request.client.host to the X-Forwarded-For client by the
    time this runs. That is ONLY trustworthy because the API is not directly
    reachable: compose binds it to 127.0.0.1 with nginx as the sole public
    entrypoint, precisely so a direct caller cannot spoof X-Forwarded-For.
    If the API is ever exposed publicly, per-IP limiting becomes bypassable.

    Falls back to "unknown" when there is no client (ASGI test transports),
    which buckets such callers together — fine, since they are not the
    internet.
    """
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client else None
    return host or "unknown"


def enforce_rate_limit(identity: str, scope: str, setting_name: str,
                       window_seconds: int = 3600) -> None:
    """Consume one rate-limit slot. Call this INSIDE the handler, not as a
    route dependency.

    Ordering is the whole point. Applied as `dependencies=[...]` on the route,
    this check runs BEFORE FastAPI validates the request body, so a malformed
    payload that never becomes a real request still burns a slot. With
    RATE_LIMIT_STRATEGIES=2 that is brutal: two typo'd submissions lock the
    user out for a full hour having created nothing. Verified live on
    2026-08-20 -- two 422s followed by two 429s, with zero strategies created.

    FastAPI validates path/query/body parameters before it executes the handler
    body, so calling this as the handler's first statement means only requests
    that are actually well-formed can consume quota. Business-rule rejections
    that happen further down (404 unknown product, 409 wrong status) still
    consume, which is intended -- those are well-formed requests that did real
    lookup work.

    `identity` is whatever the limit is scoped to, not necessarily a user id:
    business endpoints pass the authenticated user's id, while the
    unauthenticated auth endpoints pass "ip:<addr>" and "acct:<email>". It is
    only ever used to build the Redis key.

    tests/test_rate_limit_ordering.py asserts both halves of this: that a 422
    costs nothing, and that no rate-limited route reintroduces a route-level
    limiter dependency.
    """
    from app.core.config import settings as _settings

    max_calls = getattr(_settings, setting_name, None)
    if not max_calls or max_calls <= 0:
        return  # unset or explicitly disabled

    try:
        from app.core.redis_client import get_sync_redis

        redis = get_sync_redis()
        key = _rl_key(identity, scope)
        count, ttl = _get_counter(redis, key, window_seconds)
    except Exception as exc:  # Redis down: fail open, same as the dependency
        logger.warning("rate_limit.redis_error", error=str(exc), endpoint=scope)
        return

    if count > int(max_calls):
        logger.warning(
            "rate_limit.exceeded",
            user_id=identity,
            endpoint=scope,
            count=count,
            limit=int(max_calls),
        )
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "retry_after": max(ttl, 1),
                "limit": int(max_calls),
                "window": window_seconds,
            },
            headers={"Retry-After": str(max(ttl, 1))},
        )


def _current_user_dep():
    """Imported lazily: app.api.deps imports from app.core, so a module-level
    import here would be circular."""
    from app.api.deps import get_current_user

    return get_current_user


def get_user_rate_limit_state(user_id: str) -> dict[str, dict]:
    """
    Return all current rate-limit counters for a user.
    Used by GET /admin/rate-limits/{user_id}.
    """
    from app.core.redis_client import get_sync_redis
    try:
        redis = get_sync_redis()
        pattern = f"rate:{user_id}:*"
        keys = redis.keys(pattern)
        result: dict[str, dict] = {}
        for key in keys:
            slug = key.decode() if isinstance(key, bytes) else key
            slug = slug.replace(f"rate:{user_id}:", "")
            count = redis.get(key)
            ttl = redis.ttl(key)
            result[slug] = {
                "count": int(count) if count else 0,
                "ttl_seconds": ttl,
            }
        return result
    except Exception as e:
        logger.warning("rate_limit.get_state_failed", user_id=user_id, error=str(e))
        return {}


def reset_user_rate_limits(user_id: str) -> int:
    """
    Delete all rate-limit counters for a user.
    Used by POST /admin/rate-limits/reset/{user_id}.
    Returns number of keys deleted.
    """
    from app.core.redis_client import get_sync_redis
    try:
        redis = get_sync_redis()
        pattern = f"rate:{user_id}:*"
        keys = redis.keys(pattern)
        if keys:
            return redis.delete(*keys)
        return 0
    except Exception as e:
        logger.warning("rate_limit.reset_failed", user_id=user_id, error=str(e))
        return 0
