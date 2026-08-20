"""Shared Redis clients.

get_sync_redis()  — process-wide singleton redis.Redis (Celery tasks, health checks)
get_redis()       — async client for FastAPI request handlers

Connection URL comes from REDIS_URL (same variable Celery uses).
"""
from __future__ import annotations

import os
from functools import lru_cache

import redis as _redis


def _redis_url() -> str:
    # app.config (M1) exposes redis_url; fall back to env for workers started
    # without the app package fully imported.
    try:
        from app.config import settings as _s
        url = getattr(_s, "redis_url", None)
        if url:
            return url
    except Exception:
        pass
    return os.getenv("REDIS_URL", "redis://localhost:6379/0")


@lru_cache(maxsize=1)
def get_sync_redis() -> "_redis.Redis":
    """Singleton synchronous client. decode_responses=True → str in/out."""
    return _redis.Redis.from_url(_redis_url(), decode_responses=True)


_async_client = None


def get_redis():
    """Async client (redis.asyncio). Lazily created, shared per process."""
    global _async_client
    if _async_client is None:
        from redis import asyncio as aioredis
        _async_client = aioredis.from_url(_redis_url(), decode_responses=True)
    return _async_client
