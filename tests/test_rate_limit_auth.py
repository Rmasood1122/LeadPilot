"""Login and signup must be brute-force limited.

RATE_LIMIT_AUTH was defined in app/core/config.py and documented as
"POST /auth/* per 15-min window" since M8-C5 — and referenced by ZERO routes.
Login and signup accepted unlimited credential guesses. It was one of four
RATE_LIMIT_* settings in that state; the other three are still unwired and
flagged in CLAUDE_CODE_HANDOFF.md rather than guessed at.

Verified live on 2026-08-20 against the running stack: ten wrong-password
POSTs to /auth/login returned 401, the eleventh returned 429 with
`Retry-After: 880`, and a correct password immediately after the window was
cleared returned 200.

Two keys, both governed by RATE_LIMIT_AUTH:

    ip:<addr>     one host brute-forcing passwords
    acct:<email>  credential stuffing spread across many IPs at one account,
                  which a per-IP limit alone does nothing about

These tests pin both dimensions independently, plus the two things that must
NOT break: a legitimate first-attempt login, and the Finding 3 ordering
guarantee that a 422 costs nothing.
"""

import inspect

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.db import models as m
from app.db.base import get_db
from app.main import app

LIMIT = 3  # pinned low so the tests stay fast; production default is 10
PASSWORD = "CorrectHorse!1"
VICTIM = "victim@example.com"


def _route_for(path: str, method: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f"route not found: {method} {path}")


class _WithClientIP:
    """Test-only ASGI shim that sets the scope's client address.

    client_ip() reads request.client.host, which in production is rewritten by
    uvicorn's ProxyHeadersMiddleware. TestClient hard-codes ("testclient", ...)
    with no way to override it, and httpx.ASGITransport — which does accept a
    `client` tuple — is async-only on httpx 0.28, so a sync client cannot drive
    it. This shim sets scope["client"] from a test header, leaving the app and
    client_ip() itself completely unmodified.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            headers = dict(scope.get("headers") or [])
            raw = headers.get(b"x-test-client-ip")
            if raw:
                scope = {**scope, "client": (raw.decode(), 5000)}
        await self.app(scope, receive, send)


# ---------------------------------------------------------------------------
# Structural — the wiring itself (same shape as test_rate_limit_ordering.py)
# ---------------------------------------------------------------------------
AUTH_LIMITED_ROUTES = [("/auth/login", "POST"), ("/auth/signup", "POST")]


@pytest.mark.parametrize("path,method", AUTH_LIMITED_ROUTES)
def test_auth_route_enforces_the_limit(path, method):
    """The tripwire: this setting was inert for a whole milestone."""
    source = inspect.getsource(_route_for(path, method).endpoint)
    assert "enforce_rate_limit(" in source, (
        f"{method} {path} never calls enforce_rate_limit — RATE_LIMIT_AUTH is inert"
    )
    assert "RATE_LIMIT_AUTH" in source, (
        f"{method} {path} is limited by the wrong setting"
    )


@pytest.mark.parametrize("path,method", AUTH_LIMITED_ROUTES)
def test_auth_route_has_no_route_level_limiter(path, method):
    """Route-level limiters run before body validation — see Finding 3."""
    names = [
        getattr(d.call, "__qualname__", "") or getattr(d.call, "__name__", "")
        for d in _route_for(path, method).dependant.dependencies
    ]
    assert "rate_limit" not in " ".join(names).lower(), (
        f"{method} {path} has a route-level rate-limit dependency: {names}"
    )


def test_login_limits_both_ip_and_account():
    """A per-IP limit alone does not stop distributed credential stuffing."""
    source = inspect.getsource(_route_for("/auth/login", "POST").endpoint)
    assert 'f"ip:{client_ip(request)}"' in source, "login must limit per IP"
    assert 'f"acct:{email}"' in source, "login must ALSO limit per target account"


def test_refresh_is_deliberately_not_limited():
    """Legitimate clients hit /auth/refresh every 15 minutes by design.

    Limiting it would throttle normal use, and a signed refresh token is not
    brute-forceable. If this ever changes, change it deliberately.
    """
    source = inspect.getsource(_route_for("/auth/refresh", "POST").endpoint)
    assert "enforce_rate_limit(" not in source


# ---------------------------------------------------------------------------
# Behavioural — real requests, real counters
# ---------------------------------------------------------------------------
class TestAuthBruteForce:
    @pytest.fixture()
    def limited(self, monkeypatch, fake_redis):
        monkeypatch.setattr("app.core.redis_client.get_sync_redis", lambda: fake_redis)
        from app.core.config import settings

        monkeypatch.setattr(settings, "RATE_LIMIT_AUTH", LIMIT)
        return fake_redis

    @pytest.fixture()
    def victim(self, db_session):
        """A real account with a real bcrypt hash — no stubbed auth."""
        from app.services import auth as auth_svc

        user = m.User(email=VICTIM, password_hash=auth_svc.hash_password(PASSWORD))
        db_session.add(user)
        db_session.commit()
        return user

    @pytest.fixture()
    def client_from(self, db_session):
        """Build a client with a controllable source IP.

        The shim above sets the ASGI scope's client tuple, which is exactly
        what client_ip() reads — so IP rotation is exercised for real rather
        than simulated by poking Redis directly.
        """
        def _make(ip: str) -> TestClient:
            app.dependency_overrides[get_db] = lambda: db_session
            return TestClient(
                _WithClientIP(app), headers={"X-Test-Client-IP": ip}
            )

        yield _make
        app.dependency_overrides.clear()

    @staticmethod
    def _login(client, password, email=VICTIM):
        return client.post("/auth/login", json={"email": email, "password": password})

    def test_repeated_failures_trigger_429_at_the_threshold(
        self, limited, victim, client_from
    ):
        c = client_from("203.0.113.7")
        codes = [self._login(c, f"WrongGuess!{i}").status_code for i in range(LIMIT + 2)]
        assert codes[:LIMIT] == [401] * LIMIT, f"first {LIMIT} must be plain 401s: {codes}"
        assert codes[LIMIT:] == [429, 429], f"limit must engage after {LIMIT}: {codes}"

    def test_refusal_carries_retry_after(self, limited, victim, client_from):
        c = client_from("203.0.113.8")
        for i in range(LIMIT):
            self._login(c, f"WrongGuess!{i}")
        r = self._login(c, "WrongGuess!x")
        assert r.status_code == 429
        assert int(r.headers["Retry-After"]) > 0
        body = r.json()["detail"]
        assert body["error"] == "rate_limit_exceeded"
        assert body["limit"] == LIMIT
        assert body["window"] == 900, "auth uses a 15-minute window, not an hour"

    def test_legitimate_login_is_unaffected(self, limited, victim, client_from):
        """The fix must not inconvenience real users on normal use."""
        r = self._login(client_from("203.0.113.9"), PASSWORD)
        assert r.status_code == 200, r.text
        assert r.json()["access_token"]

    def test_legitimate_login_still_works_after_a_couple_of_typos(
        self, limited, victim, client_from
    ):
        """A user who mistypes once or twice must still get in."""
        c = client_from("203.0.113.10")
        assert self._login(c, "Mistyped!11").status_code == 401
        assert self._login(c, PASSWORD).status_code == 200

    def test_account_limit_survives_ip_rotation(self, limited, victim, client_from):
        """The credential-stuffing case: one account, many source IPs."""
        for i in range(LIMIT):
            r = self._login(client_from(f"198.51.100.{i}"), f"WrongGuess!{i}")
            assert r.status_code == 401

        # A brand-new IP, so its per-IP bucket is empty — the per-account
        # bucket is the only thing that can stop this.
        r = self._login(client_from("198.51.100.200"), "WrongGuess!z")
        assert r.status_code == 429, (
            "per-IP limiting alone lets an attacker rotate IPs indefinitely"
        )

    def test_ip_limit_covers_attacks_spread_across_accounts(
        self, limited, victim, client_from
    ):
        """The other direction: one host, many target accounts."""
        c = client_from("203.0.113.99")
        for i in range(LIMIT):
            r = self._login(c, "WrongGuess!1", email=f"target{i}@example.com")
            assert r.status_code == 401

        r = self._login(c, "WrongGuess!1", email="target-fresh@example.com")
        assert r.status_code == 429, (
            "per-account limiting alone lets one host spray many accounts"
        )

    def test_malformed_request_costs_nothing(self, limited, victim, client_from):
        """Finding 3's ordering guarantee, applied to auth."""
        c = client_from("203.0.113.50")
        for _ in range(LIMIT + 2):
            # Under the 8-char minimum, so it fails validation before the handler.
            assert self._login(c, "short").status_code == 422

        assert not limited.keys("rate:*"), "a 422 created a rate-limit counter"
        assert self._login(c, PASSWORD).status_code == 200, (
            "malformed requests consumed the real quota"
        )

    def test_signup_is_limited_per_ip(self, limited, client_from):
        """Unlimited signups let one caller farm accounts."""
        c = client_from("203.0.113.60")
        codes = [
            c.post(
                "/auth/signup",
                json={"email": f"farm{i}@example.com", "password": PASSWORD},
            ).status_code
            for i in range(LIMIT + 1)
        ]
        assert codes[:LIMIT] == [201] * LIMIT, codes
        assert codes[LIMIT] == 429, codes

    def test_signup_and_login_share_the_ip_budget(self, limited, victim, client_from):
        """Both spend the same auth_ip bucket — an attacker cannot alternate
        between the two endpoints to double their allowance."""
        c = client_from("203.0.113.70")
        for i in range(LIMIT):
            c.post(
                "/auth/signup",
                json={"email": f"mix{i}@example.com", "password": PASSWORD},
            )
        assert self._login(c, PASSWORD).status_code == 429
