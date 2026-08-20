"""A request that fails validation must not cost the user a rate-limit slot.

The limiter was applied as a route-level `dependencies=[...]`, which FastAPI
resolves BEFORE it validates the request body. So a malformed payload — the
kind that never becomes a real request and never reaches a single line of
business logic — still incremented the counter. With RATE_LIMIT_STRATEGIES=2
that meant two typo'd submissions locked a user out for a full hour having
created nothing at all.

Verified live on 2026-08-20 against the running stack: four POSTs to
/products/{id}/strategies, the first two carrying an invalid flow_type. The
result was 422, 422, 429, 429 — quota fully spent, zero strategies created.

The fix moves the check inside the handler, where FastAPI guarantees the body
has already been validated. These tests pin BOTH halves: that a 422 costs
nothing, and that nobody moves the check back above validation.
"""

import inspect

import pytest
from fastapi.routing import APIRoute

from app.db import models as m
from app.main import app

# Every route that consumes a rate-limit slot. Add new paid endpoints here.
RATE_LIMITED_ROUTES = [
    ("/products/{product_id}/strategies", "POST"),
    ("/strategies/{strategy_id}/leads/source", "POST"),
]


def _route_for(path: str, method: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f"route not found: {method} {path}")


@pytest.mark.parametrize("path,method", RATE_LIMITED_ROUTES)
def test_no_route_level_limiter_dependency(path, method):
    """The regression guard.

    A route-level limiter runs before body validation, which is exactly the
    bug. If someone reintroduces `dependencies=[Depends(rate_limit_dependency(
    ...))]`, this fails.
    """
    route = _route_for(path, method)
    names = [
        getattr(d.call, "__qualname__", "") or getattr(d.call, "__name__", "")
        for d in route.dependant.dependencies
    ]
    flat = " ".join(names)
    assert "rate_limit" not in flat.lower(), (
        f"{method} {path} has a route-level rate-limit dependency: {names}. "
        "That runs BEFORE body validation, so malformed requests burn quota. "
        "Call enforce_rate_limit() inside the handler instead."
    )


@pytest.mark.parametrize("path,method", RATE_LIMITED_ROUTES)
def test_limit_is_consumed_before_any_side_effect(path, method):
    """enforce_rate_limit must be the handler's first real statement.

    Validation is handled by FastAPI before the body runs, but the limiter
    still has to come before any DB lookup or enqueue — otherwise a caller
    could do real work on every request and only then be told to slow down.
    """
    route = _route_for(path, method)
    body = inspect.getsource(route.endpoint)
    # Strip signature + docstring, then find the first executable statement.
    lines = [
        ln.strip()
        for ln in body.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    try:
        doc_end = next(
            i for i, ln in enumerate(lines) if ln.endswith('"""') and i > 0
        )
    except StopIteration:  # pragma: no cover - every handler here has a docstring
        doc_end = 0
    first_stmt = next(
        ln for ln in lines[doc_end + 1:] if not ln.startswith(("@", "def ", ")"))
    )
    assert "enforce_rate_limit(" in first_stmt, (
        f"{method} {path}: expected enforce_rate_limit() as the first "
        f"statement, found {first_stmt!r}"
    )


class TestMalformedRequestsAreFree:
    """The behavioural half, against a real client and a real counter."""

    @pytest.fixture()
    def limited(self, monkeypatch, fake_redis):
        """Route the limiter at fakeredis and pin the limit at 2."""
        monkeypatch.setattr(
            "app.core.redis_client.get_sync_redis", lambda: fake_redis
        )
        from app.core.config import settings

        monkeypatch.setattr(settings, "RATE_LIMIT_STRATEGIES", 2)
        return fake_redis

    @pytest.fixture()
    def product_id(self, db_session, test_user):
        product = m.Product(
            user=test_user,
            name="Rate limit probe",
            description="A product used only to exercise the limiter",
            type=m.ProductType.PRODUCT,
        )
        db_session.add(product)
        db_session.commit()
        return product.id

    def _post(self, client, product_id, flow_type):
        return client.post(
            f"/products/{product_id}/strategies", json={"flow_type": flow_type}
        )

    def test_invalid_body_does_not_consume_quota(self, client, limited, product_id):
        # Two malformed requests: flow_type is not a member of the enum.
        for _ in range(2):
            r = self._post(client, product_id, "definitely-not-valid")
            assert r.status_code == 422, r.text

        assert not limited.keys("rate:*"), (
            "a 422 created a rate-limit counter; validation must come first"
        )

        # Quota untouched, so both valid requests still succeed.
        for attempt in range(2):
            r = self._post(client, product_id, "no_clients")
            assert r.status_code == 202, (
                f"valid request #{attempt + 1} was rejected ({r.status_code}); "
                "the malformed requests consumed quota"
            )

    def test_limiter_still_fires_on_valid_requests(self, client, limited, product_id):
        """Fixing the ordering must not disable the limit."""
        for _ in range(2):
            assert self._post(client, product_id, "no_clients").status_code == 202

        r = self._post(client, product_id, "no_clients")
        assert r.status_code == 429
        assert r.json()["detail"]["error"] == "rate_limit_exceeded"

    def test_malformed_then_valid_still_hits_the_limit_at_the_right_count(
        self, client, limited, product_id
    ):
        """The exact live reproduction: 422, 422, then the real quota intact."""
        self._post(client, product_id, "bad-one")
        self._post(client, product_id, "bad-two")
        codes = [
            self._post(client, product_id, "no_clients").status_code
            for _ in range(3)
        ]
        assert codes == [202, 202, 429], (
            f"expected the two 422s to be free, got {codes}"
        )
