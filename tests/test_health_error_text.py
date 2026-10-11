"""Health endpoints never return raw exception text (platform-gaps item 4).

GET /health is public and used to put the Celery heartbeat check's exception
message straight into `components.celery.error`; GET /health/channels (any
signed-in user) did the same for its Redis reads. Redis client errors name
hosts and ports ("Error 111 connecting to redis.internal:6379"). Both now
answer a fixed string and log the detail.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.redis_client import get_redis
from app.db.base import get_db

SECRET_TEXT = "Error 111 connecting to redis-internal.example:6379. Connection refused."


class _LeakyRedis:
    """PING works, every GET raises with infrastructure detail in the text."""

    async def ping(self):
        return True

    async def get(self, key):
        raise ConnectionError(SECRET_TEXT)


@pytest.fixture()
def logged(monkeypatch):
    """What the two health loggers were asked to log (structlog does not go
    through caplog)."""
    from app.api import health
    from app.services import health_checks

    calls: list[str] = []

    class _Recorder:
        def __init__(self, real):
            self._real = real

        def error(self, event, **kw):
            calls.append(f"{event} {kw}")

        def __getattr__(self, name):
            return getattr(self._real, name)

    monkeypatch.setattr(health_checks, "logger", _Recorder(health_checks.logger))
    monkeypatch.setattr(health, "logger", _Recorder(health.logger))
    return calls


@pytest.fixture()
def health_client(db_session, test_user):
    from app.api import deps
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: _LeakyRedis()
    app.dependency_overrides[deps.get_current_user] = lambda: test_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_public_health_hides_the_celery_exception(health_client, logged):
    r = health_client.get("/health")
    assert r.status_code == 200
    assert r.json()["components"]["celery"] == {"status": "degraded",
                                                "error": "heartbeat check failed"}
    assert "redis-internal" not in r.text and "6379" not in r.text
    assert any("health.celery_check_failed" in c and "redis-internal" in c
               for c in logged)  # the detail is logged, not lost


def test_channel_health_hides_exception_text(health_client, logged):
    r = health_client.get("/health/channels")
    assert r.status_code == 200
    body = r.json()
    for name in ("gmail", "whatsapp", "calendly"):
        assert body["channels"][name] == {"status": "unknown", "error": "check failed"}, name
    assert "redis-internal" not in r.text and "6379" not in r.text
    assert sum("health.channel_check_failed" in c and "redis-internal" in c
               for c in logged) == 3


def test_admin_learning_loop_hides_exception_text(db_session, test_user, logged):
    """Admin-only, but the same rule: no exception text in a response."""
    from app.api import deps
    from app.main import app

    test_user.is_admin = True
    db_session.commit()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_redis] = lambda: _LeakyRedis()
    app.dependency_overrides[deps.require_admin] = lambda: test_user
    try:
        r = TestClient(app).get("/health/learning-loop")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json() == {"status": "unknown", "error": "check failed"}
    assert "redis-internal" not in r.text
    assert any("health.learning_loop_check_failed" in c and "redis-internal" in c
               for c in logged)
