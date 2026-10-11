"""The /status page in the main frontend (www.calendarharvest.com/status/)
reads GET /status/public from the visitor's browser. Its component ids,
names and status vocabulary are hard-coded in
frontend/src/lib/statusBoard.ts; this test fails if the backend contract in
app/api/status_public.py changes without that file changing with it.

Offline: reads two files from the repository.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.api import status_public

REPO = Path(__file__).resolve().parents[1]
BOARD = REPO / "frontend" / "src" / "lib" / "statusBoard.ts"
LINK = REPO / "frontend" / "src" / "lib" / "statusPage.ts"
PAGE = REPO / "frontend" / "src" / "app" / "status" / "page.tsx"


def _block(source: str, name: str) -> str:
    match = re.search(rf"export const {name}\b[^=]*=\s*(\[.*?\])", source, flags=re.S)
    assert match, f"{name} not found in {BOARD}"
    return match.group(1)


def test_known_components_match_the_backend_in_order():
    pairs = re.findall(
        r'\{\s*id:\s*"([^"]+)",\s*name:\s*"([^"]+)"\s*\}',
        _block(BOARD.read_text(encoding="utf-8"), "KNOWN_COMPONENTS"),
    )
    assert tuple(pairs) == status_public.COMPONENTS


def test_status_vocabulary_matches_the_backend():
    values = re.findall(r'"([a-z_]+)"', _block(BOARD.read_text(encoding="utf-8"), "PUBLIC_STATUSES"))
    assert tuple(values) == status_public.PUBLIC_STATUSES


def test_browser_get_from_a_configured_origin_gets_cors_headers(db_session, monkeypatch):
    """The page calls /status/public from the visitor's browser. The global
    CORSMiddleware answers a simple GET from any CORS_ORIGINS entry (in
    production that list must hold https://www.calendarharvest.com — a
    founder-side check, see docs/program/STATUS_PAGE.md) and from nothing
    else. No auth header, no cookies: the request the page sends."""
    import fakeredis
    from fastapi.testclient import TestClient

    from app import main
    from app.core.redis_client import get_redis
    from app.db.base import get_db

    from app.services import health_checks

    async def _no_network_probe(api_key):  # the Anthropic Models API probe
        return {"status": "ok"}

    monkeypatch.setattr(health_checks, "_probe_models_endpoint", _no_network_probe)
    health_checks.reset_ai_probe_cache()
    allowed = main._ENV_ORIGINS[0]
    status_public.reset_cache()
    main.app.dependency_overrides[get_db] = lambda: db_session
    main.app.dependency_overrides[get_redis] = lambda: fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        client = TestClient(main.app)
        ok = client.get("/status/public", headers={"Origin": allowed})
        assert ok.status_code == 200
        assert ok.headers.get("access-control-allow-origin") == allowed
        assert ok.text.startswith('{"components":[')

        other = client.get("/status/public", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in other.headers
    finally:
        main.app.dependency_overrides.clear()
        status_public.reset_cache()
        health_checks.reset_ai_probe_cache()


def test_page_is_public_and_linked_with_a_trailing_slash():
    # Outside the authenticated (app) route group, so no session is needed.
    assert PAGE.is_file()
    assert "(app)" not in PAGE.as_posix()
    link = LINK.read_text(encoding="utf-8")
    assert re.search(r'export const STATUS_PAGE_URL = "/status/";', link)
    assert re.search(r"export const SHOW_STATUS_LINK = true;", link)
