"""Architecture tripwire: a URL in config must point at a route that exists.

GMAIL_REDIRECT_URI was `.../api/v1/integrations/gmail/callback` in all four
places it is defined (app/core/config.py, .env, .env.example,
.env.production.example). app/main.py mounts every router UNPREFIXED — the real
path is /integrations/gmail/callback, and **0 of the app's 78 mounted paths
start with /api/v1**. Google would have redirected the user to a 404 and the
OAuth flow could never complete, with nothing failing until someone actually
tried to connect a Gmail account.

This is the same writers-vs-readers mismatch that produced the Celery queue
outage and the CORS format break: config describing an interface the app does
not have.
"""

import os
import re
from urllib.parse import urlparse

import pytest
from fastapi.routing import APIRoute

from app.core.config import Settings
from app.main import app

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENV_FILES = [".env.example", ".env.production.example"]

# config key -> the HTTP method its path must be reachable by
CONFIG_URLS_TO_ROUTES = {"GMAIL_REDIRECT_URI": "GET"}


def _mounted_paths() -> set[str]:
    return {r.path for r in app.routes if isinstance(r, APIRoute)}


def _path_matches_route(path: str, routes: set[str]) -> bool:
    """Exact match, or match a parameterised route like /x/{id}/y."""
    if path in routes:
        return True
    for route in routes:
        pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+", re.escape(route)
                               .replace(r"\{", "{").replace(r"\}", "}")) + "$"
        if re.match(pattern, path):
            return True
    return False


def test_no_mounted_route_uses_an_api_v1_prefix():
    """Pins the fact the stale config assumed. If a versioned prefix is ever
    introduced, this test should fail and the config URLs updated with it."""
    versioned = [p for p in _mounted_paths() if p.startswith("/api/v1")]
    assert not versioned, (
        f"routes now exist under /api/v1 ({versioned[:3]}); config URLs that "
        f"were corrected to the unprefixed form need revisiting"
    )


@pytest.mark.parametrize("setting,method", CONFIG_URLS_TO_ROUTES.items())
def test_config_url_points_at_a_real_route(setting, method):
    value = getattr(Settings(), setting)
    assert value, f"{setting} is empty"
    path = urlparse(value).path
    routes = _mounted_paths()
    assert _path_matches_route(path, routes), (
        f"{setting} points at {path!r}, which is not a mounted route. "
        f"Closest matches: "
        f"{sorted(r for r in routes if path.split('/')[-1] in r)[:3]}"
    )


@pytest.mark.parametrize("filename", _ENV_FILES)
@pytest.mark.parametrize("setting", list(CONFIG_URLS_TO_ROUTES))
def test_shipped_env_templates_use_a_real_route(filename, setting):
    """The templates operators copy must not reintroduce the dead path."""
    with open(os.path.join(_ROOT, filename), encoding="utf-8") as handle:
        lines = [l.strip() for l in handle if l.strip().startswith(f"{setting}=")]
    assert lines, f"{filename}: no {setting} line"
    routes = _mounted_paths()
    for line in lines:
        path = urlparse(line.split("=", 1)[1]).path
        assert _path_matches_route(path, routes), (
            f"{filename}: {setting} points at {path!r}, not a mounted route"
        )
