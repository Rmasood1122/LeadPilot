"""Shared plumbing — retry, cache, circuit breaker, logging."""

import json

import httpx
import pytest

from app.integrations.plumbing import (
    BaseHttpAdapter,
    CircuitBreaker,
    CircuitOpenError,
    ExternalAPIError,
    RateLimitExceeded,
)


class DummyAdapter(BaseHttpAdapter):
    provider = "dummy"
    base_url = "https://dummy.test"


def make_adapter(fake_redis, handler, **kwargs) -> tuple[DummyAdapter, list]:
    sleeps: list[float] = []
    adapter = DummyAdapter(
        redis=fake_redis,
        http=httpx.Client(base_url="https://dummy.test", transport=httpx.MockTransport(handler)),
        sleep=sleeps.append,
        **kwargs,
    )
    return adapter, sleeps


class TestRetry:
    def test_429_retried_with_retry_after_then_succeeds(self, fake_redis):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(429, headers={"Retry-After": "7"}, json={})
            return httpx.Response(200, json={"ok": True})

        adapter, sleeps = make_adapter(fake_redis, handler)
        assert adapter.call("GET", "/x")["ok"] is True
        assert calls["n"] == 3
        assert sleeps == [7.0, 7.0], "Retry-After header wins over exponential backoff"

    def test_5xx_uses_exponential_backoff(self, fake_redis):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(503, json={})
            return httpx.Response(200, json={"ok": True})

        adapter, sleeps = make_adapter(fake_redis, handler)
        adapter.call("GET", "/x")
        assert sleeps == [2.0, 4.0], "base * 2^(attempt-1)"

    def test_persistent_429_raises_rate_limit_exceeded(self, fake_redis):
        adapter, _ = make_adapter(fake_redis, lambda r: httpx.Response(429, json={}))
        with pytest.raises(RateLimitExceeded):
            adapter.call("GET", "/x")

    def test_non_retryable_4xx_fails_immediately(self, fake_redis):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(401, json={"error": "bad key"})

        adapter, _ = make_adapter(fake_redis, handler)
        with pytest.raises(ExternalAPIError) as err:
            adapter.call("GET", "/x")
        assert calls["n"] == 1, "401 must not be retried"
        assert err.value.status == 401


class TestCache:
    def test_identical_call_served_from_cache(self, fake_redis):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={"n": calls["n"]})

        adapter, _ = make_adapter(fake_redis, handler)
        first = adapter.call("GET", "/x", params={"q": 1}, cache_ttl=60)
        second = adapter.call("GET", "/x", params={"q": 1}, cache_ttl=60)
        assert first == second and calls["n"] == 1

    def test_different_params_are_different_cache_keys(self, fake_redis):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={"n": calls["n"]})

        adapter, _ = make_adapter(fake_redis, handler)
        adapter.call("GET", "/x", params={"q": 1}, cache_ttl=60)
        adapter.call("GET", "/x", params={"q": 2}, cache_ttl=60)
        assert calls["n"] == 2

    def test_no_ttl_means_no_caching(self, fake_redis):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={})

        adapter, _ = make_adapter(fake_redis, handler)
        adapter.call("GET", "/x")
        adapter.call("GET", "/x")
        assert calls["n"] == 2


class TestCircuitBreaker:
    def _failing_adapter(self, fake_redis, threshold=2):
        adapter, _ = make_adapter(fake_redis, lambda r: httpx.Response(500, json={}))
        adapter.breaker = CircuitBreaker(
            "dummy", fake_redis, failure_threshold=threshold, cooldown_seconds=60
        )
        return adapter

    def test_opens_after_threshold_and_fails_fast(self, fake_redis):
        adapter = self._failing_adapter(fake_redis, threshold=2)
        for _ in range(2):
            with pytest.raises(ExternalAPIError):
                adapter.call("GET", "/boom")
        with pytest.raises(CircuitOpenError) as err:
            adapter.call("GET", "/boom")
        assert 0 < err.value.retry_in_seconds <= 60
        assert adapter.breaker.is_open()

    def test_success_resets_failure_count(self, fake_redis):
        state = {"fail": True}

        def handler(request):
            return httpx.Response(500 if state["fail"] else 200, json={})

        adapter, _ = make_adapter(fake_redis, handler)
        adapter.breaker = CircuitBreaker("dummy", fake_redis, failure_threshold=3, cooldown_seconds=60)

        with pytest.raises(ExternalAPIError):
            adapter.call("GET", "/x")
        state["fail"] = False
        adapter.call("GET", "/x")  # success wipes the failure counter
        state["fail"] = True
        for _ in range(2):  # 2 < threshold 3 → still closed
            with pytest.raises(ExternalAPIError):
                adapter.call("GET", "/x")
        assert not adapter.breaker.is_open()

    def test_breaker_state_shared_across_adapter_instances(self, fake_redis):
        a1 = self._failing_adapter(fake_redis, threshold=1)
        with pytest.raises(ExternalAPIError):
            a1.call("GET", "/boom")
        a2, _ = make_adapter(fake_redis, lambda r: httpx.Response(200, json={}))
        a2.breaker = CircuitBreaker("dummy", fake_redis, failure_threshold=1, cooldown_seconds=60)
        with pytest.raises(CircuitOpenError):
            a2.call("GET", "/anything")


class TestStructuredLogging:
    def test_every_call_emits_one_json_record(self, fake_redis, caplog):
        adapter, _ = make_adapter(fake_redis, lambda r: httpx.Response(200, json={}))
        with caplog.at_level("INFO", logger="leadpilot.external"):
            adapter.call("GET", "/things", cost_units=5)
        records = [json.loads(r.message) for r in caplog.records
                   if r.name == "leadpilot.external"]
        assert len(records) == 1
        rec = records[0]
        assert rec["provider"] == "dummy"
        assert rec["endpoint"] == "/things"
        assert rec["status"] == 200
        assert rec["cost_units"] == 5
        assert rec["cached"] is False
        assert "latency_ms" in rec
