"""
Chunk 5 — Production Launch tests (20 tests)

Coverage:
  Rate limiting      (5)
  Plan enforcement   (5)
  Webhook delivery   (5)
  Onboarding         (4)
  Benchmark dry-run  (1)
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    store: dict = {}
    counters: dict = {}
    redis = MagicMock()

    def incr_side_effect(key):
        counters[key] = counters.get(key, 0) + 1
        return counters[key]

    def ttl_side_effect(key):
        return 3600 if key in store or key in counters else -2

    pipe = MagicMock()
    pipe.incr = MagicMock(side_effect=lambda k: None)
    pipe.ttl = MagicMock(side_effect=lambda k: None)
    pipe.execute = MagicMock(return_value=[1, 3600])
    redis.pipeline.return_value = pipe

    redis.incr = MagicMock(side_effect=incr_side_effect)
    redis.get = MagicMock(side_effect=lambda k: store.get(k))
    redis.set = MagicMock(side_effect=lambda k, v, ex=None: store.__setitem__(k, v))
    redis.expire = MagicMock()
    redis.ttl = MagicMock(side_effect=ttl_side_effect)
    redis.delete = MagicMock(side_effect=lambda *keys: len(keys))
    redis.keys = MagicMock(return_value=[])
    return redis


@pytest.fixture
def mock_user_free():
    user = MagicMock()
    user.id = "user-free-001"
    user.plan = "free"
    return user


@pytest.fixture
def mock_user_pro():
    user = MagicMock()
    user.id = "user-pro-001"
    user.plan = "pro"
    return user


@pytest.fixture
def mock_db():
    return MagicMock()


# ===========================================================================
# Rate limiting (5 tests)
# ===========================================================================

class TestRateLimiting:

    def test_get_counter_increments(self, mock_redis):
        from app.core.rate_limiting import _get_counter
        mock_redis.pipeline.return_value.execute.return_value = [1, 3600]
        count, ttl = _get_counter(mock_redis, "rate:user-1:test_ep", 3600)
        assert count == 1

    def test_limit_exceeded_raises_http_429(self, mock_redis):
        """_get_counter returns 11 (over limit of 10) → HTTPException 429."""
        from app.core.rate_limiting import check_rate_limit
        from fastapi import HTTPException

        mock_redis.pipeline.return_value.execute.return_value = [11, 60]

        with patch("app.core.redis_client.get_sync_redis", return_value=mock_redis):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(check_rate_limit(
                    request=MagicMock(),
                    user_id="user-1",
                    endpoint_slug="test_ep",
                    max_calls=10,
                    window_seconds=3600,
                ))
        assert exc_info.value.status_code == 429

    def test_fails_open_on_redis_error(self, mock_redis):
        """Redis connection failure → request passes through (fail open)."""
        from app.core.rate_limiting import check_rate_limit

        mock_redis.pipeline.side_effect = Exception("Redis down")

        with patch("app.core.redis_client.get_sync_redis", return_value=mock_redis):
            # Should NOT raise
            asyncio.run(check_rate_limit(
                request=MagicMock(),
                user_id="user-1",
                endpoint_slug="test_ep",
                max_calls=10,
                window_seconds=3600,
            ))

    def test_get_user_rate_limit_state(self, mock_redis):
        from app.core.rate_limiting import get_user_rate_limit_state
        mock_redis.keys.return_value = [b"rate:user-1:strategies", b"rate:user-1:leads"]
        mock_redis.get.return_value = b"3"
        mock_redis.ttl.return_value = 1800

        with patch("app.core.redis_client.get_sync_redis", return_value=mock_redis):
            state = get_user_rate_limit_state("user-1")
        assert "strategies" in state or len(state) == 2

    def test_reset_clears_all_counters(self, mock_redis):
        from app.core.rate_limiting import reset_user_rate_limits
        mock_redis.keys.return_value = [b"rate:user-1:strategies", b"rate:user-1:leads"]
        mock_redis.delete.return_value = 2

        with patch("app.core.redis_client.get_sync_redis", return_value=mock_redis):
            deleted = reset_user_rate_limits("user-1")
        assert deleted == 2


# ===========================================================================
# Plan enforcement (5 tests)
# ===========================================================================

class TestPlanEnforcement:

    def test_free_plan_strategy_limit(self, mock_user_free):
        from app.core.plans import check_plan_limit, PlanLimitExceeded
        with pytest.raises(PlanLimitExceeded) as exc_info:
            check_plan_limit(mock_user_free, "max_strategies", current_count=3)
        assert exc_info.value.current_plan == "free"
        assert exc_info.value.upgrade_to == "starter"

    def test_pro_plan_no_limit(self, mock_user_pro):
        from app.core.plans import check_plan_limit
        # Should not raise — pro has unlimited
        check_plan_limit(mock_user_pro, "max_strategies", current_count=999)

    def test_feature_check_blocks_free_plan(self, mock_user_free):
        from app.core.plans import check_feature, PlanLimitExceeded
        with pytest.raises(PlanLimitExceeded):
            check_feature(mock_user_free, "multi_variate")

    def test_feature_check_allows_pro(self, mock_user_pro):
        from app.core.plans import check_feature
        check_feature(mock_user_pro, "multi_variate")  # should not raise

    def test_channel_check_rejects_whatsapp_on_free(self, mock_user_free):
        from app.core.plans import check_channel, PlanLimitExceeded
        with pytest.raises(PlanLimitExceeded) as exc_info:
            check_channel(mock_user_free, "whatsapp")
        assert "whatsapp" in exc_info.value.message.lower()

    # Note: only 5 tests allocated to plan — but we included an extra above
    # so moving the 6th into the 5-slot allocation of rate-limiting would
    # break the test count. Keeping as-is (tests are cumulative).


# ===========================================================================
# Webhook delivery (5 tests)
# ===========================================================================

class TestWebhookDelivery:
    """app/services/webhook_delivery.py, on the real PostgreSQL schema.

    These five tests were written for the M8-C5 module, whose API was
    create_delivery(db_session=, target_id=, event_type=, payload=) -> id | None
    and mark_failed_attempt(db, id, status, error, attempt) -> bool. Commit
    41cea92 rebuilt the module (its docstring explains why: the old raw SQL
    never delivered anything on PostgreSQL) and removed both functions, so
    four of these tests failed on import or signature before testing anything.

    Each test keeps its name and the behaviour it pinned, restated against the
    current API: a delivery row is inserted and queued; an event nobody
    subscribed to produces no delivery; a failed attempt with retries left is
    rescheduled; a failed final attempt is terminal. They used to run against
    a MagicMock session, so they now also prove the rows persist on Postgres.
    """

    URL = "https://hooks.example.com/leadpilot"

    @pytest.fixture()
    def target(self, db_session, monkeypatch):
        import uuid as _uuid

        from app.db.models import User
        from app.services import webhook_delivery

        # Delivery re-resolves the host (SSRF guard). Answer with a public
        # address instead of doing a DNS lookup: the suite stays offline.
        monkeypatch.setattr(webhook_delivery, "_resolve", lambda host: ["93.184.216.34"])
        user = User(email=f"hooks_{_uuid.uuid4().hex[:8]}@test.io", email_verified=True)
        db_session.add(user)
        db_session.commit()
        target, _secret = webhook_delivery.create_target(
            db_session, user.id, self.URL, ["meeting_booked"])
        return target

    @staticmethod
    def _answer(monkeypatch, status: int) -> list:
        import httpx

        from app.services import webhook_delivery

        calls: list = []

        def handler(request):
            calls.append(request)
            return httpx.Response(status)

        monkeypatch.setattr(webhook_delivery, "_http",
                            lambda: httpx.Client(transport=httpx.MockTransport(handler)))
        return calls

    def test_create_delivery_inserts_row(self, db_session, target, queued_jobs):
        from app.db.models import WebhookDelivery
        from app.services.webhook_delivery import create_delivery

        delivery = create_delivery(db_session, target, "meeting_booked", {"lead_id": "lead-1"})

        assert delivery is not None
        assert len(str(delivery.id)) == 36  # UUID length
        db_session.expire_all()
        row = db_session.get(WebhookDelivery, delivery.id)
        assert row is not None and row.status == "pending" and row.attempts == 0
        assert row.payload_json["data"] == {"lead_id": "lead-1"}
        # ... and it was queued for delivery, as deliver_webhook.delay was.
        # (queued_jobs stores every non-bool argument as a string.)
        assert (str(delivery.id), "0") in queued_jobs["webhooks"]

    def test_unknown_event_type_returns_none(self, db_session, target, queued_jobs):
        from app.db.models import WebhookDelivery
        from app.services.webhook_delivery import fire_event

        # The event hub enters through fire_event; an event no target is
        # subscribed to must produce no delivery at all.
        result = fire_event(db_session, target.user_id, "unknown_event", {})

        assert result == []
        assert db_session.query(WebhookDelivery).count() == 0
        assert queued_jobs["webhooks"] == []

    def test_retry_delays_correct_length(self):
        from app.services.webhook_delivery import RETRY_DELAYS_SECONDS
        assert len(RETRY_DELAYS_SECONDS) == 5
        assert RETRY_DELAYS_SECONDS[0] == 30
        assert RETRY_DELAYS_SECONDS[-1] == 7200

    def test_mark_failed_returns_true_if_retries_remain(
            self, db_session, target, queued_jobs, monkeypatch):
        from app.db.models import WebhookDelivery
        from app.services.webhook_delivery import create_delivery, deliver

        calls = self._answer(monkeypatch, 500)
        delivery = create_delivery(db_session, target, "meeting_booked", {}, enqueue=False)

        has_more = deliver(db_session, delivery.id)   # attempt 1 of 6

        assert has_more == "retry"
        assert len(calls) == 1
        db_session.expire_all()
        row = db_session.get(WebhookDelivery, delivery.id)
        assert row.status == "pending" and row.attempts == 1
        assert row.last_status_code == 500 and row.next_attempt_at is not None
        assert (str(delivery.id), "30") in queued_jobs["webhooks"]

    def test_mark_failed_returns_false_when_exhausted(
            self, db_session, target, queued_jobs, monkeypatch):
        from app.db.models import WebhookDelivery
        from app.services.webhook_delivery import RETRY_DELAYS_SECONDS, create_delivery, deliver

        calls = self._answer(monkeypatch, 500)
        delivery = create_delivery(db_session, target, "meeting_booked", {}, enqueue=False)
        delivery.attempts = len(RETRY_DELAYS_SECONDS)   # five failures so far
        db_session.commit()

        has_more = deliver(db_session, delivery.id)   # attempt 6 of 6 (1 + 5 retries)

        assert has_more == "exhausted"
        assert len(calls) == 1
        db_session.expire_all()
        row = db_session.get(WebhookDelivery, delivery.id)
        assert row.status == "exhausted" and row.next_attempt_at is None
        assert queued_jobs["webhooks"] == []   # nothing rescheduled


# ===========================================================================
# Onboarding (4 tests)
# ===========================================================================

class TestOnboarding:

    def test_mark_complete_is_idempotent(self, mock_db):
        """Calling mark_complete twice for the same step should only add it once."""
        from app.api.onboarding import mark_complete, _get_state

        # First call
        with patch("app.api.onboarding._get_state", return_value={"step_completed": []}):
            mark_complete(mock_db, "user-1", "product_created")

        # Call execute count before second call
        call_count_after_first = mock_db.execute.call_count

        # Second call — same step
        with patch("app.api.onboarding._get_state",
                   return_value={"step_completed": ["product_created"]}):
            mark_complete(mock_db, "user-1", "product_created")

        # Should NOT have issued another UPDATE (still at same execute count)
        assert mock_db.execute.call_count == call_count_after_first

    def test_invalid_step_ignored(self, mock_db):
        from app.api.onboarding import mark_complete
        # Should not raise, just return
        mark_complete(mock_db, "user-1", "invalid_step_xyz")
        mock_db.execute.assert_not_called()

    def test_all_steps_list_correct_length(self):
        from app.api.onboarding import ONBOARDING_STEPS
        assert len(ONBOARDING_STEPS) == 7

    def test_step_descriptions_all_defined(self):
        from app.api.onboarding import ONBOARDING_STEPS, STEP_DESCRIPTIONS
        for step in ONBOARDING_STEPS:
            assert step in STEP_DESCRIPTIONS, f"Missing description for step: {step}"


# ===========================================================================
# Benchmark dry-run (1 test)
# ===========================================================================

class TestBenchmark:

    def test_benchmark_dry_run_passes(self):
        """Dry run should complete without raising and report no FAILs."""
        import asyncio
        from scripts.benchmark import main
        exit_code = asyncio.run(main(dry_run=True, json_output=False))
        assert exit_code == 0, "Dry-run benchmark reported FAIL grade(s)"
