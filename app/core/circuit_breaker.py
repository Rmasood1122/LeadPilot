"""
Circuit breaker for external API integrations.

Extends the M2 implementation with:
  - State introspection endpoint support (get_all_states())
  - circuit_opened outcome event written when a circuit opens
  - Admin FCM notification on circuit open
  - Env-driven failure threshold and recovery timeout

States:
  CLOSED     — normal operation, requests pass through
  OPEN       — failure threshold exceeded, requests fast-fail
  HALF_OPEN  — recovery probe: one request allowed; success → CLOSED, failure → OPEN

Configuration (from .env / Settings):
  CIRCUIT_BREAKER_FAILURE_THRESHOLD  — default 5
  CIRCUIT_BREAKER_RECOVERY_TIMEOUT   — default 60 (seconds)
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

from app.core.logging import get_logger

logger = get_logger("core.circuit_breaker")

T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreakerState:
    provider: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float | None = None
    next_retry_time: float | None = None
    total_opens: int = 0
    last_opened_at: float | None = None


# Global registry of all circuit breaker instances
_registry: dict[str, "CircuitBreaker"] = {}
_registry_lock = threading.Lock()


def get_all_states() -> list[dict[str, Any]]:
    """Return snapshot of all circuit breaker states — used by /admin/circuit-breakers."""
    with _registry_lock:
        states = []
        for name, cb in _registry.items():
            s = cb._state
            states.append({
                "provider": s.provider,
                "state": s.state.value,
                "failure_count": s.failure_count,
                "last_failure_time": s.last_failure_time,
                "next_retry_time": s.next_retry_time,
                "total_opens": s.total_opens,
                "last_opened_at": s.last_opened_at,
            })
        return states


class CircuitBreaker:
    """
    Thread-safe circuit breaker with side-effects on state transitions.

    Usage:
        cb = CircuitBreaker("apollo")

        @cb.protect
        def search_leads(params):
            return apollo_client.search(params)
    """

    def __init__(
        self,
        provider: str,
        failure_threshold: int | None = None,
        recovery_timeout: int | None = None,
    ):
        from app.core.config import settings
        self.provider = provider
        self.failure_threshold = (
            failure_threshold or settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD
        )
        self.recovery_timeout = (
            recovery_timeout or settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT
        )
        self._state = CircuitBreakerState(provider=provider)
        self._lock = threading.Lock()

        # Register globally
        with _registry_lock:
            _registry[provider] = self

    @property
    def is_open(self) -> bool:
        with self._lock:
            self._maybe_transition_to_half_open()
            return self._state.state == CircuitState.OPEN

    def _maybe_transition_to_half_open(self) -> None:
        """Called while holding _lock. Transition OPEN → HALF_OPEN if recovery timeout passed."""
        if (
            self._state.state == CircuitState.OPEN
            and self._state.next_retry_time is not None
            and time.monotonic() >= self._state.next_retry_time
        ):
            self._state.state = CircuitState.HALF_OPEN
            logger.info(
                "circuit_breaker.half_open",
                provider=self.provider,
                failure_count=self._state.failure_count,
            )

    def record_success(self) -> None:
        with self._lock:
            if self._state.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info(
                    "circuit_breaker.closed",
                    provider=self.provider,
                    was_open_for=int(time.time() - (self._state.last_opened_at or time.time())),
                )
            self._state.state = CircuitState.CLOSED
            self._state.failure_count = 0
            self._state.last_failure_time = None
            self._state.next_retry_time = None

    def record_failure(self) -> None:
        with self._lock:
            self._state.failure_count += 1
            self._state.last_failure_time = time.time()

            if self._state.failure_count >= self.failure_threshold:
                was_closed = self._state.state == CircuitState.CLOSED
                self._state.state = CircuitState.OPEN
                self._state.next_retry_time = time.monotonic() + self.recovery_timeout

                if was_closed:
                    self._state.total_opens += 1
                    self._state.last_opened_at = time.time()
                    logger.error(
                        "circuit_breaker.opened",
                        provider=self.provider,
                        failure_count=self._state.failure_count,
                        recovery_timeout_seconds=self.recovery_timeout,
                    )
                    # Side-effects: outcome event + admin FCM notification
                    # These are fire-and-forget (best effort) — don't crash the circuit breaker
                    self._on_circuit_opened()

    def _on_circuit_opened(self) -> None:
        """
        Side-effects when the circuit opens. Run in background (best effort).
        1. Write circuit_opened outcome event
        2. Send admin FCM notification
        """
        import threading
        threading.Thread(target=self._write_open_side_effects, daemon=True).start()

    def _write_open_side_effects(self) -> None:
        try:
            # 1. Write outcome event
            from app.core.database import SessionLocal
            from app.models.outcome import Outcome, OutcomeEvent
            import datetime

            db = SessionLocal()
            try:
                db.add(Outcome(
                    lead_id=None,
                    strategy_id=None,
                    event=OutcomeEvent.circuit_opened,
                    data={"provider": self.provider, "failure_count": self._state.failure_count},
                    ts=datetime.datetime.utcnow(),
                ))
                db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning("circuit_breaker.outcome_write_failed", provider=self.provider, error=str(e))

        try:
            # 2. Admin FCM notification
            from app.services.notification_service import NotificationService
            import asyncio
            asyncio.run(NotificationService.send_to_admins(
                title="Integration Temporarily Paused",
                body=(
                    f"{self.provider.title()} integration is temporarily paused — "
                    f"retrying in {self.recovery_timeout // 60} minutes."
                ),
                data={"event": "circuit_opened", "provider": self.provider},
            ))
        except Exception as e:
            logger.warning("circuit_breaker.fcm_notify_failed", provider=self.provider, error=str(e))

    def protect(self, func: Callable[..., T]) -> Callable[..., T]:
        """
        Decorator that wraps a function with circuit breaker logic.

        Usage:
            @circuit_breaker.protect
            def call_apollo():
                ...
        """
        import functools

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            with self._lock:
                self._maybe_transition_to_half_open()
                current_state = self._state.state

            if current_state == CircuitState.OPEN:
                raise CircuitOpenError(
                    f"Circuit for {self.provider} is OPEN — "
                    f"retry after {self._state.next_retry_time}"
                )

            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except CircuitOpenError:
                raise
            except Exception as e:
                self.record_failure()
                logger.warning(
                    "circuit_breaker.failure_recorded",
                    provider=self.provider,
                    error=str(e),
                    failure_count=self._state.failure_count,
                    threshold=self.failure_threshold,
                )
                raise

        return wrapper


class CircuitOpenError(Exception):
    """Raised when a call is attempted through an OPEN circuit."""
    pass
