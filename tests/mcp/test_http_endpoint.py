"""/mcp over real HTTP (FastAPI TestClient, app lifespan running).

What Claude's client depends on: a 401 with `WWW-Authenticate: Bearer
resource_metadata=...` when unauthenticated, RFC 9728 metadata whose
`resource` is the MCP URL exactly, a stateless server (no Mcp-Session-Id),
and token separation between the web API and the connector.
"""

from __future__ import annotations

from app.config import settings
from tests.conftest import auth_headers
from tests.mcp.conftest import RESOURCE, mcp_token

ACCEPT = {"Accept": "application/json, text/event-stream",
          "Content-Type": "application/json"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                   "clientInfo": {"name": "test", "version": "1"}}}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
METADATA = "/.well-known/oauth-protected-resource/mcp"


def _post(client, body, token=None, **headers):
    hdrs = {**ACCEPT, "MCP-Protocol-Version": "2025-11-25", **headers}
    hdrs["Authorization"] = f"Bearer {token}" if token else ""
    return client.post("/mcp", json=body, headers=hdrs)


def test_disabled_by_default_answers_404(client, monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", False)
    assert _post(client, LIST).status_code == 404
    assert client.get(METADATA).status_code == 404


def test_unauthenticated_request_gets_401_pointing_at_the_metadata(client):
    r = _post(client, LIST)
    assert r.status_code == 401
    header = r.headers["www-authenticate"]
    assert header.startswith("Bearer ")
    assert f'resource_metadata="http://testserver{METADATA}"' in header


def test_protected_resource_metadata(client):
    r = client.get(METADATA)
    assert r.status_code == 200
    body = r.json()
    assert body["resource"] == RESOURCE
    assert body["authorization_servers"] == ["http://testserver"]
    assert set(body["scopes_supported"]) == {"leadpilot:read", "leadpilot:write",
                                             "offline_access"}


def test_production_resource_is_the_url_the_user_types(monkeypatch):
    monkeypatch.setattr(settings, "mcp_resource_url", "https://api.calendarharvest.com/mcp")
    from app.mcp.server import metadata_path, protected_resource_metadata

    meta = protected_resource_metadata()
    assert meta["resource"] == "https://api.calendarharvest.com/mcp"
    assert meta["authorization_servers"] == ["https://api.calendarharvest.com"]
    assert metadata_path() == METADATA


def test_valid_token_lists_tools_statelessly(client, world):
    token = mcp_token(world.me)
    r = _post(client, INIT, token)
    assert r.status_code == 200
    assert "mcp-session-id" not in {k.lower() for k in r.headers}
    r = _post(client, LIST, token)
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"list_leads", "search", "fetch"} <= names


def test_tool_call_over_http_reads_only_my_data(client, world):
    r = _post(client, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "list_leads", "arguments": {}}},
              mcp_token(world.me))
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is False
    assert result["structuredContent"]["total"] == 3


def test_web_session_token_is_refused_at_mcp(client, world):
    web = auth_headers(world.me)["Authorization"].removeprefix("Bearer ")
    assert _post(client, LIST, web).status_code == 401


def test_personal_api_key_is_refused_at_mcp(client, world, db_session):
    from app.services import api_keys

    _row, plaintext = api_keys.create(db_session, world.me.id, "zapier")
    assert _post(client, LIST, plaintext).status_code == 401


def test_connector_token_is_refused_by_the_rest_api(client, world):
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {mcp_token(world.me)}"})
    assert r.status_code == 401


def test_token_for_another_resource_is_refused(client, world):
    token = mcp_token(world.me, audience="https://evil.example/mcp")
    assert _post(client, LIST, token).status_code == 401


def test_expired_token_is_refused(client, world):
    assert _post(client, LIST, mcp_token(world.me, ttl_seconds=-5)).status_code == 401


def test_suspended_account_gets_401(client, world, db_session):
    token = mcp_token(world.me)
    world.me.is_suspended = True
    db_session.commit()
    assert _post(client, LIST, token).status_code == 401


def test_token_issued_before_a_password_change_is_refused(client, world, db_session):
    from datetime import datetime, timedelta, timezone

    token = mcp_token(world.me)
    world.me.password_changed_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    db_session.commit()
    assert _post(client, LIST, token).status_code == 401


def test_foreign_host_header_is_refused(client, world):
    r = _post(client, LIST, mcp_token(world.me), Host="attacker.example")
    assert r.status_code == 421
