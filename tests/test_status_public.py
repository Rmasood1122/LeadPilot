"""Phase 3 (status.calendarharvest.com): GET /status/public, and GET /health
pinned byte for byte across the extraction of its checks.

GET /health had no tests of its own before this file. Its checks were moved
into app/services/health_checks.py so /status/public could reuse them without
copying them, and the TestHealthUnchanged class below was written and run
against the ORIGINAL app/api/health.py first (see docs/program/STATUS_PAGE.md,
"Evidence") so "unchanged" is a measured claim, not an assumption. The exact
bytes matter beyond tidiness: the UptimeRobot keyword monitor matches the
literal text `{"status":"ok","components"` at the start of the healthy body.

Everything here is offline: SQLite or a session double for the database,
fakeredis or a failing double for Redis, and an injected probe for the AI
gateway, so nothing reaches api.anthropic.com.
"""

from __future__ import annotations

import time

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.core.redis_client import get_redis
from app.db.base import get_db

HEARTBEAT_KEY = "celery:heartbeat"


# ---------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------

class _BrokenSession:
    """A session whose every statement fails, like an unreachable database."""

    def execute(self, *args, **kwargs):
        raise RuntimeError("db unreachable: host db.internal.example port 5432")

    def rollback(self):
        return None

    def close(self):
        return None


class _BrokenRedis:
    """An async Redis whose every call fails, like an unreachable Upstash."""

    async def ping(self):
        raise ConnectionError("boom")

    async def get(self, key):
        raise ConnectionError("boom")


@pytest.fixture()
def async_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def make_client(db_session):
    """Build a TestClient with chosen database and Redis doubles.

    Unauthenticated on purpose: both endpoints under test are public, so a
    test that passed only because a token was attached would prove nothing.
    """
    from app.main import app

    clients = []

    def _make(*, db=None, redis=None) -> TestClient:
        app.dependency_overrides[get_db] = lambda: (db if db is not None else db_session)
        if redis is not None:
            app.dependency_overrides[get_redis] = lambda: redis
        c = TestClient(app)
        clients.append(c)
        return c

    try:
        yield _make
    finally:
        app.dependency_overrides.clear()


def _run(coro):
    import asyncio

    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# GET /health — byte-for-byte characterization
# ---------------------------------------------------------------------------

class TestHealthUnchanged:
    def test_all_healthy_exact_bytes(self, make_client, async_redis):
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time())))
        r = make_client(redis=async_redis).get("/health")
        assert r.status_code == 200
        assert r.content == (
            b'{"status":"ok","components":{"database":{"status":"ok"},'
            b'"redis":{"status":"ok"},"celery":{"status":"ok","last_beat_seconds_ago":0}}}'
        )

    def test_healthy_body_starts_with_the_keyword_monitor_text(self, make_client, async_redis):
        """The UptimeRobot keyword monitor (STATUS_PAGE.md) matches this
        prefix. A bare `"status":"ok"` would ALSO match a degraded body,
        because every healthy sub-component carries it."""
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time())))
        assert make_client(redis=async_redis).get("/health").text.startswith(
            '{"status":"ok","components"')

    def test_degraded_body_does_not_contain_the_keyword(self, make_client, async_redis):
        body = make_client(redis=async_redis).get("/health").text
        assert '"status":"ok","components"' not in body
        assert '"status":"ok"' in body  # why the bare form would be wrong

    def test_no_heartbeat_is_degraded_exact_bytes(self, make_client, async_redis):
        r = make_client(redis=async_redis).get("/health")
        assert r.status_code == 200
        assert r.content == (
            b'{"status":"degraded","components":{"database":{"status":"ok"},'
            b'"redis":{"status":"ok"},"celery":{"status":"degraded",'
            b'"reason":"no heartbeat key found"}}}'
        )

    def test_stale_heartbeat_is_degraded_exact_bytes(self, make_client, async_redis):
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time() - 500)))
        r = make_client(redis=async_redis).get("/health")
        assert r.status_code == 200
        assert r.content == (
            b'{"status":"degraded","components":{"database":{"status":"ok"},'
            b'"redis":{"status":"ok"},"celery":{"status":"degraded",'
            b'"reason":"heartbeat stale (500s ago)","last_beat_seconds_ago":500}}}'
        )

    def test_unparseable_heartbeat_is_degraded_with_a_fixed_error(self, make_client, async_redis):
        """Contract changed on purpose (platform-gaps item 4): this used to
        echo the exception text ("could not convert string to float: ...")
        on a PUBLIC endpoint. Exception text can carry hostnames and ports;
        the response now carries a fixed string and the detail is logged."""
        _run(async_redis.set(HEARTBEAT_KEY, "garbage"))
        r = make_client(redis=async_redis).get("/health")
        assert r.status_code == 200
        assert r.json()["components"]["celery"] == {
            "status": "degraded", "error": "heartbeat check failed"}
        assert "could not convert" not in r.text

    def test_database_down_is_503_exact_bytes(self, make_client, async_redis):
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time())))
        r = make_client(db=_BrokenSession(), redis=async_redis).get("/health")
        assert r.status_code == 503
        assert r.content == (
            b'{"detail":{"status":"down","components":{"database":{"status":"down",'
            b'"error":"connection failed"},"redis":{"status":"ok"},'
            b'"celery":{"status":"ok","last_beat_seconds_ago":0}}}}'
        )

    def test_redis_down_is_503_exact_bytes(self, make_client):
        # celery.error was the raw exception text ("boom") until platform-gaps
        # item 4; it is now a fixed string (the exception is logged).
        r = make_client(redis=_BrokenRedis()).get("/health")
        assert r.status_code == 503
        assert r.content == (
            b'{"detail":{"status":"down","components":{"database":{"status":"ok"},'
            b'"redis":{"status":"down","error":"ping failed"},'
            b'"celery":{"status":"degraded","error":"heartbeat check failed"}}}}'
        )

    def test_health_needs_no_authentication(self, make_client, async_redis):
        r = make_client(redis=async_redis).get("/health")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /status/public
# ---------------------------------------------------------------------------

import inspect
import re

import httpx
import respx
from fastapi.routing import APIRoute

from app.api import status_public
from app.services import health_checks

# Captured at import, before any fixture replaces it.
_REAL_PROBE = health_checks._probe_models_endpoint

EXPECTED_IDS = ["api", "background-processing", "ai-features", "booking-pages"]
EXPECTED_NAMES = {
    "api": "API",
    "background-processing": "Background processing",
    "ai-features": "AI features",
    "booking-pages": "Booking pages",
}
PUBLIC_STATUSES = {"operational", "degraded", "partial_outage", "major_outage", "maintenance"}
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class _Probe:
    """Stands in for the Anthropic Models API call; counts invocations."""

    def __init__(self, result=None):
        self.result = result or {"status": "ok"}
        self.calls = 0

    async def __call__(self, api_key):
        self.calls += 1
        return self.result


@pytest.fixture(autouse=True)
def _fresh_status_state(monkeypatch):
    """Empty caches per test, and a probe that never touches the network."""
    status_public.reset_cache()
    health_checks.reset_ai_probe_cache()
    probe = _Probe()
    monkeypatch.setattr(health_checks, "_probe_models_endpoint", probe)
    yield probe
    status_public.reset_cache()
    health_checks.reset_ai_probe_cache()


@pytest.fixture()
def probe(_fresh_status_state):
    return _fresh_status_state


class _NoBookingTablesSession:
    """Database reachable (SELECT 1 works) but the booking tables are not."""

    def __init__(self, real):
        self.real = real

    def execute(self, statement, *a, **k):
        if "calendar_" in str(statement):
            raise RuntimeError('relation "calendar_booking_pages" does not exist')
        return self.real.execute(statement, *a, **k)

    def rollback(self):
        return self.real.rollback()

    def close(self):
        return None


def _statuses(body) -> dict[str, str]:
    return {c["id"]: c["status"] for c in body["components"]}


def _assert_public_shape(resp):
    """The whole contract: nothing but these keys, ids, names and values."""
    body = resp.json()
    assert set(body) == {"components"}
    assert [c["id"] for c in body["components"]] == EXPECTED_IDS
    for comp in body["components"]:
        assert set(comp) == {"id", "name", "status", "checked_at"}
        assert comp["name"] == EXPECTED_NAMES[comp["id"]]
        assert comp["status"] in PUBLIC_STATUSES
        assert ISO_UTC.match(comp["checked_at"]), comp["checked_at"]
    return body


# Text that exists in the internal results or the doubles' exceptions and
# must never reach the public body.
_FORBIDDEN_FRAGMENTS = [
    "boom", "db.internal", "5432", "relation", "does not exist", "heartbeat",
    "celery", "redis", "database", "error", "reason", "seconds", "stale",
    "garbage", "convert", "http", "api key", "localhost", "queue",
    "last_beat", "test-key", "anthropic",
]


def _assert_no_leak(resp):
    raw = resp.text.lower()
    # Drop the fixed names, ids and statuses, then nothing internal may remain.
    for comp in resp.json()["components"]:
        raw = raw.replace(comp["checked_at"].lower(), "")
    for fragment in _FORBIDDEN_FRAGMENTS:
        assert fragment not in raw, f"{fragment!r} leaked into {resp.text}"


class TestStatusMapping:
    def test_everything_healthy_is_operational(self, make_client, async_redis):
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time())))
        r = make_client(redis=async_redis).get("/status/public")
        assert r.status_code == 200
        body = _assert_public_shape(r)
        assert set(_statuses(body).values()) == {"operational"}
        _assert_no_leak(r)

    def test_database_down(self, make_client, async_redis):
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time())))
        r = make_client(db=_BrokenSession(), redis=async_redis).get("/status/public")
        assert r.status_code == 200  # the status endpoint itself is up
        assert _statuses(_assert_public_shape(r)) == {
            "api": "major_outage",
            "background-processing": "operational",
            "ai-features": "operational",
            "booking-pages": "major_outage",
        }
        _assert_no_leak(r)

    def test_redis_down(self, make_client):
        r = make_client(redis=_BrokenRedis()).get("/status/public")
        assert r.status_code == 200
        assert _statuses(_assert_public_shape(r)) == {
            "api": "partial_outage",
            "background-processing": "major_outage",
            "ai-features": "operational",
            "booking-pages": "operational",
        }
        _assert_no_leak(r)

    def test_no_heartbeat_is_a_major_outage_of_background_processing(self, make_client, async_redis):
        r = make_client(redis=async_redis).get("/status/public")
        assert _statuses(_assert_public_shape(r))["background-processing"] == "major_outage"
        _assert_no_leak(r)

    def test_stale_heartbeat_is_degraded(self, make_client, async_redis):
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time() - 200)))
        r = make_client(redis=async_redis).get("/status/public")
        assert _statuses(_assert_public_shape(r))["background-processing"] == "degraded"
        _assert_no_leak(r)

    def test_unreadable_heartbeat_is_a_major_outage(self, make_client, async_redis):
        _run(async_redis.set(HEARTBEAT_KEY, "garbage"))
        r = make_client(redis=async_redis).get("/status/public")
        assert _statuses(_assert_public_shape(r))["background-processing"] == "major_outage"
        _assert_no_leak(r)

    def test_booking_tables_unreachable(self, make_client, async_redis, db_session):
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time())))
        r = make_client(db=_NoBookingTablesSession(db_session), redis=async_redis).get("/status/public")
        assert _statuses(_assert_public_shape(r)) == {
            "api": "operational",
            "background-processing": "operational",
            "ai-features": "operational",
            "booking-pages": "major_outage",
        }
        _assert_no_leak(r)

    @pytest.mark.parametrize("probe_result,expected", [
        ({"status": "ok"}, "operational"),
        ({"status": "degraded", "reason": "http 529"}, "degraded"),
        ({"status": "degraded", "reason": "unreachable"}, "degraded"),
        ({"status": "down", "reason": "http 401"}, "major_outage"),
    ])
    def test_ai_gateway_results(self, make_client, async_redis, probe, probe_result, expected):
        probe.result = probe_result
        r = make_client(redis=async_redis).get("/status/public")
        assert _statuses(_assert_public_shape(r))["ai-features"] == expected
        _assert_no_leak(r)

    def test_no_anthropic_key_is_a_major_outage_without_probing(
            self, make_client, async_redis, probe, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "")
        r = make_client(redis=async_redis).get("/status/public")
        assert _statuses(_assert_public_shape(r))["ai-features"] == "major_outage"
        assert probe.calls == 0
        _assert_no_leak(r)

    def test_everything_down_still_answers_and_leaks_nothing(self, make_client, probe):
        probe.result = {"status": "down", "reason": "http 401"}
        r = make_client(db=_BrokenSession(), redis=_BrokenRedis()).get("/status/public")
        assert r.status_code == 200
        assert set(_statuses(_assert_public_shape(r)).values()) == {"major_outage"}
        _assert_no_leak(r)

    def test_backend_never_emits_maintenance(self):
        """`maintenance` is in the contract for the status site's incident
        files; no backend check may claim it."""
        src = inspect.getsource(status_public)
        body = src.split("def api_status", 1)[1]
        assert "MAINTENANCE" not in body


class TestAiGatewayProbe:
    """The real probe function, with httpx mocked by respx (no network)."""

    @pytest.fixture(autouse=True)
    def _real_probe(self, monkeypatch, _fresh_status_state):
        monkeypatch.setattr(health_checks, "_probe_models_endpoint", _REAL_PROBE)

    @pytest.mark.parametrize("status_code,expected", [
        (200, "ok"), (401, "down"), (403, "down"), (404, "down"),
        (429, "degraded"), (500, "degraded"), (529, "degraded"),
    ])
    def test_http_status_mapping(self, status_code, expected):
        with respx.mock(assert_all_called=True) as mock:
            route = mock.get(health_checks.ANTHROPIC_MODELS_URL).mock(
                return_value=httpx.Response(status_code, json={}))
            result = _run(health_checks.check_ai_gateway("sk-test"))
        assert result["status"] == expected
        sent = route.calls.last.request
        assert sent.headers["x-api-key"] == "sk-test"
        assert sent.url.params["limit"] == "1"
        assert sent.method == "GET"  # the Models API: no tokens billed

    def test_timeout_is_degraded(self):
        with respx.mock() as mock:
            mock.get(health_checks.ANTHROPIC_MODELS_URL).mock(
                side_effect=httpx.ConnectTimeout("timed out"))
            result = _run(health_checks.check_ai_gateway("sk-test"))
        assert result == {"status": "degraded", "reason": "unreachable"}

    def test_result_is_cached_and_a_new_key_reprobes(self):
        with respx.mock() as mock:
            route = mock.get(health_checks.ANTHROPIC_MODELS_URL).mock(
                return_value=httpx.Response(200, json={}))
            _run(health_checks.check_ai_gateway("sk-one"))
            _run(health_checks.check_ai_gateway("sk-one"))
            assert route.call_count == 1
            _run(health_checks.check_ai_gateway("sk-two"))
            assert route.call_count == 2

    def test_cache_expires(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(health_checks.time, "monotonic", lambda: clock[0])
        with respx.mock() as mock:
            route = mock.get(health_checks.ANTHROPIC_MODELS_URL).mock(
                return_value=httpx.Response(200, json={}))
            _run(health_checks.check_ai_gateway("sk-one"))
            clock[0] += health_checks.AI_PROBE_TTL_SECONDS + 1
            _run(health_checks.check_ai_gateway("sk-one"))
            assert route.call_count == 2


class TestCaching:
    def test_second_call_within_30s_is_served_from_cache(self, make_client, async_redis, monkeypatch):
        calls = {"db": 0}
        real = health_checks.check_database

        def counting(db):
            calls["db"] += 1
            return real(db)

        monkeypatch.setattr(health_checks, "check_database", counting)
        client = make_client(redis=async_redis)
        first = client.get("/status/public")
        assert _statuses(first.json())["background-processing"] == "major_outage"
        # The world gets better, but the cached answer stands for 30 s.
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time())))
        second = client.get("/status/public")
        assert second.json() == first.json()
        assert calls["db"] == 1

    def test_cache_expires_after_30s(self, make_client, async_redis, monkeypatch):
        clock = [5000.0]
        monkeypatch.setattr(status_public.time, "monotonic", lambda: clock[0])
        client = make_client(redis=async_redis)
        assert _statuses(client.get("/status/public").json())["background-processing"] == "major_outage"
        _run(async_redis.set(HEARTBEAT_KEY, str(time.time())))
        clock[0] += 29
        assert _statuses(client.get("/status/public").json())["background-processing"] == "major_outage"
        clock[0] += 2
        assert _statuses(client.get("/status/public").json())["background-processing"] == "operational"

    def test_cache_control_header(self, make_client, async_redis):
        r = make_client(redis=async_redis).get("/status/public")
        assert r.headers["cache-control"] == "public, max-age=30"


class TestRateLimit:
    def test_limit_per_ip_returns_429_with_retry_after(self, make_client, async_redis, monkeypatch):
        from app.core.config import settings as core

        monkeypatch.setattr(core, "RATE_LIMIT_PUBLIC_STATUS", 2)
        client = make_client(redis=async_redis)
        assert client.get("/status/public").status_code == 200
        assert client.get("/status/public").status_code == 200  # cache hit still counts
        r = client.get("/status/public")
        assert r.status_code == 429
        assert int(r.headers["retry-after"]) >= 1
        assert r.json()["detail"]["error"] == "rate_limit_exceeded"

    def test_default_limit_is_positive(self):
        from app.core.config import Settings

        assert Settings().RATE_LIMIT_PUBLIC_STATUS > 0

    def test_limiter_is_the_first_statement_and_not_a_route_dependency(self):
        route = next(r for r in __import__("app.main", fromlist=["app"]).app.routes
                     if isinstance(r, APIRoute) and r.path == "/status/public")
        names = " ".join(getattr(d.call, "__qualname__", "") for d in route.dependant.dependencies)
        assert "rate_limit" not in names.lower()
        src = inspect.getsource(route.endpoint)
        after_doc = src.split('"""', 2)[2]
        first = next(ln.strip() for ln in after_doc.splitlines() if ln.strip())
        assert first.startswith("enforce_rate_limit(") and "RATE_LIMIT_PUBLIC_STATUS" in first


class TestPublicAccess:
    def test_reachable_without_a_token(self, make_client, async_redis):
        client = make_client(redis=async_redis)
        assert "authorization" not in {k.lower() for k in client.headers}
        assert client.get("/status/public").status_code == 200

    def test_route_has_no_auth_dependency(self):
        from app.main import app

        route = next(r for r in app.routes
                     if isinstance(r, APIRoute) and r.path == "/status/public")
        deps = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
        assert not deps & {"get_current_user", "require_admin", "get_current_active_user"}
        assert route.methods == {"GET"}

    def test_health_still_has_no_auth_dependency(self):
        from app.main import app

        route = next(r for r in app.routes if isinstance(r, APIRoute) and r.path == "/health")
        deps = {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}
        assert "get_current_user" not in deps
