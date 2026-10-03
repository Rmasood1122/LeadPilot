"""F9 — the test-only /debug router is reachable ONLY in dev / local / test.

It was refused in production, prod and live -- a denylist. Staging (or any
other deployed environment whose name is not on that list) with
ENABLE_DEBUG_ROUTES=true therefore served endpoints that fabricate leads,
change the send cap and mint unsubscribe tokens.

The rule is now an allowlist: the router exists only when the dedicated flag
is on AND the environment is one of development, dev, local, test, testing.
Anything else -- staging, production, a typo, an empty value -- is refused.

POST /debug/set-send-cap is kept (the integration compliance suite uses it).
"""

import os
import subprocess
import sys

import pytest

from app.config import get_settings

ALLOWED = ["development", "dev", "local", "test", "testing", "  Development  ", "TEST"]
REFUSED = ["staging", "stage", "production", "prod", "live", "qa", "preview", "", "prodution"]


@pytest.fixture()
def settings_env(monkeypatch):
    """Set app_env / the flag on the cached settings object for one test."""
    settings = get_settings()

    def _set(env: str, flag: bool = True):
        monkeypatch.setattr(settings, "app_env", env)
        monkeypatch.setattr(settings, "enable_debug_routes", flag)
        return settings

    return _set


class TestTheMountDecision:
    """Settings.debug_routes_allowed is what app/main.py mounts on."""

    @pytest.mark.parametrize("env", ALLOWED)
    def test_allowed_in_dev_local_and_test(self, settings_env, env):
        assert settings_env(env).debug_routes_allowed is True

    @pytest.mark.parametrize("env", REFUSED)
    def test_refused_everywhere_else(self, settings_env, env):
        assert settings_env(env).debug_routes_allowed is False

    @pytest.mark.parametrize("env", ALLOWED + REFUSED)
    def test_never_allowed_without_the_dedicated_flag(self, settings_env, env):
        assert settings_env(env, flag=False).debug_routes_allowed is False

    def test_main_mounts_on_that_decision_and_nothing_else(self):
        import inspect

        import app.main as main

        source = inspect.getsource(main)
        assert "debug_routes_allowed" in source
        assert 'not in {"production", "prod", "live"}' not in source


class TestTheImportTimeGuard:
    """Layer 3: app.api.debug refuses to define its router outside dev/test,
    even if something imports it directly."""

    @pytest.mark.parametrize("env", REFUSED)
    def test_it_raises_outside_dev_local_test(self, settings_env, env):
        from app.api import debug

        settings_env(env)
        with pytest.raises(RuntimeError, match="test-only"):
            debug._refuse_outside_dev_and_test()

    @pytest.mark.parametrize("env", ALLOWED)
    def test_it_is_silent_in_dev_local_test(self, settings_env, env):
        from app.api import debug

        settings_env(env)
        debug._refuse_outside_dev_and_test()


class TestSetSendCapIsKept:
    def test_the_route_still_exists_and_works_in_the_test_environment(
            self, client, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings, "gmail_daily_cap", settings.gmail_daily_cap)
        monkeypatch.setattr(settings, "gmail_warmup_start_sends",
                            settings.gmail_warmup_start_sends)
        monkeypatch.setattr(settings, "gmail_warmup_daily_increment",
                            settings.gmail_warmup_daily_increment)

        response = client.post("/debug/set-send-cap", json={"daily_cap": 2})
        assert response.status_code == 200, response.text
        assert response.json()["daily_cap"] == 2

    def test_whatsapp_status_is_behind_the_same_router(self):
        from app.api import debug

        paths = {route.path for route in debug.router.routes}
        assert "/debug/set-send-cap" in paths
        assert "/debug/whatsapp-status" in paths


def _debug_paths_in_a_fresh_app(app_env: str) -> str:
    """Import app.main in a clean interpreter with the flag ON and report
    whether any /debug route exists."""
    env = dict(os.environ, APP_ENV=app_env, ENABLE_DEBUG_ROUTES="true")
    code = (
        "from app.main import app\n"
        "paths = [r.path for r in app.routes if getattr(r, 'path', '').startswith('/debug')]\n"
        "print('DEBUG_ROUTES=%d' % len(paths))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                            text=True, timeout=300,
                            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert result.returncode == 0, result.stderr[-2000:]
    return [line for line in result.stdout.splitlines()
            if line.startswith("DEBUG_ROUTES=")][-1]


class TestTheRealAppInAFreshProcess:
    """End to end: the flag is ON in both cases; only the environment differs."""

    def test_staging_serves_no_debug_route(self):
        assert _debug_paths_in_a_fresh_app("staging") == "DEBUG_ROUTES=0"

    def test_development_serves_the_debug_routes(self):
        assert _debug_paths_in_a_fresh_app("development") != "DEBUG_ROUTES=0"
