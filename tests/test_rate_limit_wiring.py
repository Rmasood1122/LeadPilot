"""Architecture tripwire: a configured rate limit must actually be applied.

Every RATE_LIMIT_* setting existed, `app/core/rate_limiting.py` implemented a
decorator, a dependency helper and two admin endpoints for inspecting and
resetting counters — and NOT ONE route was ever limited. Verified live on
2026-08-20: six consecutive POST /products/{id}/strategies calls against a
limit of 2 returned six 202s. The most expensive operation in the system
(~150 Claude calls per invocation) was completely unbounded.

Two reasons it could never have worked:
  * the `rate_limit` decorator's wrapper is `async def` and `await`s the
    endpoint, but every route needing a limit is a sync `def`;
  * it raises `app.core.rate_limiting.RateLimitExceeded`, for which no
    exception handler is registered, so it would surface as 500 not 429.
    (Note there is a SECOND, unrelated `RateLimitExceeded` in
    app/integrations/plumbing.py — same name, different class.)

`enforce_rate_limit`, called as the handler's FIRST statement, is the working
path. These tests assert the expensive endpoints keep using it. If you add a
paid or model-backed endpoint, add it here.

It was originally `rate_limit_dependency` applied as `dependencies=[...]` on
the route. That worked, but ran BEFORE FastAPI validated the request body, so
a malformed payload burned a slot without creating anything — with a limit of
2/hour, two typos locked the user out for an hour. The check moved inside the
handler; test_rate_limit_ordering.py guards the ordering itself.
"""

import inspect

import pytest
from fastapi.routing import APIRoute

from app.core.config import Settings
from app.main import app

# endpoint path -> the settings key that must govern it
RATE_LIMITED_ROUTES = {
    ("/products/{product_id}/strategies", "POST"): "RATE_LIMIT_STRATEGIES",
    ("/strategies/{strategy_id}/leads/source", "POST"): "RATE_LIMIT_LEADS_SOURCE",
}


def _route_for(path: str, method: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f"route not found: {method} {path}")


@pytest.mark.parametrize("path,method,setting", [
    (p, m, s) for (p, m), s in RATE_LIMITED_ROUTES.items()
])
def test_expensive_route_enforces_its_rate_limit(path, method, setting):
    """The handler must call enforce_rate_limit with its governing setting."""
    route = _route_for(path, method)
    source = inspect.getsource(route.endpoint)
    assert "enforce_rate_limit(" in source, (
        f"{method} {path} never calls enforce_rate_limit; its RATE_LIMIT_* "
        f"setting is inert."
    )
    assert setting in source, (
        f"{method} {path} calls enforce_rate_limit but not with {setting}."
    )


@pytest.mark.parametrize("path,method,setting", [
    (p, m, s) for (p, m), s in RATE_LIMITED_ROUTES.items()
])
def test_governing_setting_exists_and_is_positive(path, method, setting):
    """A limit of 0/None disables the check — never ship that by accident."""
    value = getattr(Settings(), setting)
    assert isinstance(value, int) and value > 0, (
        f"{setting} governs {method} {path} but is {value!r}"
    )


def test_strategy_limit_stays_conservative_for_launch():
    """Guards the deliberate 10 -> 2 reduction from silently drifting back up.

    Raising it is a real decision (each strategy is ~150 Claude calls); this
    test exists so raising it is explicit rather than accidental.
    """
    assert Settings().RATE_LIMIT_STRATEGIES <= 3, (
        "RATE_LIMIT_STRATEGIES was raised above the launch ceiling. If that is "
        "intentional, update this test and app/core/config.py's rationale."
    )


def test_decorator_is_not_used_on_any_route():
    """The decorator cannot work here — catch anyone reaching for it.

    It wraps the endpoint in an `async def` that awaits it, which breaks the
    sync routes, and raises an unhandled exception type.
    """
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        wrapped = getattr(route.endpoint, "__wrapped__", None)
        if wrapped is not None:
            module = getattr(route.endpoint, "__module__", "")
            assert "rate_limiting" not in module, (
                f"{route.path} uses the @rate_limit decorator, which cannot "
                f"work on this codebase's sync routes; use "
                f"rate_limit_dependency instead"
            )
