"""The connector's OAuth 2.1 authorization server, end to end over HTTP.

The flow Claude runs: metadata -> DCR -> /oauth/authorize (PKCE S256) ->
consent (signed-in person) -> code -> /oauth/token -> /mcp -> refresh ->
rotation, with a reused refresh token answered `invalid_grant` and its family
revoked. Plus the refusals: PKCE mismatch, wrong redirect URI, code reuse,
another tenant's data, scopes, revocation, disabled server.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit

import pytest

from app.config import settings
from tests.mcp.conftest import RESOURCE

CLAUDE = "https://claude.ai/api/mcp/auth_callback"
CHATGPT = "https://chatgpt.com/connector_platform_oauth_redirect"
ISSUER = "http://testserver"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
MCP_HEADERS = {"Accept": "application/json, text/event-stream",
               "Content-Type": "application/json", "MCP-Protocol-Version": "2025-11-25"}


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def register(client, redirect_uris=(CLAUDE,), **extra):
    return client.post("/oauth/register", json={"redirect_uris": list(redirect_uris),
                                                "client_name": "Claude", **extra})


def authorize(client, client_id, challenge, *, redirect_uri=CLAUDE, state="st-1",
              scope="leadpilot:read leadpilot:write offline_access", **extra):
    params = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri,
              "code_challenge": challenge, "code_challenge_method": "S256",
              "state": state, "scope": scope, "resource": RESOURCE, **extra}
    return client.get("/oauth/authorize", params={k: v for k, v in params.items()
                                                  if v is not None},
                      follow_redirects=False)


def query(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def approve(client, location, *, approve=True):
    request_id = query(location)["request"]
    r = client.post(f"/oauth/requests/{request_id}/decision", json={"approve": approve})
    assert r.status_code == 200, r.text
    return r.json()["redirect_to"]


def exchange(client, client_id, code, verifier, *, redirect_uri=CLAUDE):
    return client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": redirect_uri, "client_id": client_id, "resource": RESOURCE},
        headers=FORM)


def refresh(client, client_id, refresh_token):
    return client.post("/oauth/token", data={
        "grant_type": "refresh_token", "refresh_token": refresh_token,
        "client_id": client_id}, headers=FORM)


def connect(client, *, scope="leadpilot:read leadpilot:write offline_access"):
    """The whole Claude handshake. Returns (client_id, token response)."""
    client_id = register(client).json()["client_id"]
    verifier, challenge = pkce()
    location = authorize(client, client_id, challenge, scope=scope).headers["location"]
    code = query(approve(client, location))["code"]
    r = exchange(client, client_id, code, verifier)
    assert r.status_code == 200, r.text
    return client_id, r.json()


def mcp_call(client, access_token, name="list_leads", arguments=None):
    return client.post("/mcp", headers={**MCP_HEADERS, "Authorization": f"Bearer {access_token}"},
                       json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                             "params": {"name": name, "arguments": arguments or {}}})


# ---------------------------------------------------------------------------
# Discovery and registration
# ---------------------------------------------------------------------------


def test_authorization_server_metadata(client):
    r = client.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    meta = r.json()
    assert meta["issuer"] == ISSUER
    # The same string the protected-resource metadata names (ChatGPT compares).
    prm = client.get("/.well-known/oauth-protected-resource/mcp").json()
    assert prm["authorization_servers"] == [meta["issuer"]]
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert meta["token_endpoint_auth_methods_supported"] == ["none"]
    assert meta["authorization_response_iss_parameter_supported"] is True
    assert "offline_access" in meta["scopes_supported"]
    assert set(meta["grant_types_supported"]) == {"authorization_code", "refresh_token"}
    for key in ("authorization_endpoint", "token_endpoint", "registration_endpoint",
                "revocation_endpoint"):
        assert meta[key].startswith(ISSUER + "/oauth/")


def test_disabled_server_answers_404(client, monkeypatch):
    monkeypatch.setattr(settings, "mcp_enabled", False)
    assert client.get("/.well-known/oauth-authorization-server").status_code == 404
    assert register(client).status_code == 404
    assert client.post("/oauth/token", data={}, headers=FORM).status_code == 404


@pytest.mark.parametrize("uris", [
    [CLAUDE], [CHATGPT], ["http://localhost:53682/callback"],
    ["http://127.0.0.1/callback", CLAUDE],
])
def test_registration_accepts_the_known_callbacks(client, uris):
    r = register(client, uris)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["client_id"].startswith("lpc_")
    assert body["token_endpoint_auth_method"] == "none"
    assert body["redirect_uris"] == uris
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("uris", [
    ["https://evil.example/callback"], ["https://claude.ai/api/mcp/auth_callback/x"],
    ["http://localhost/other"], ["https://localhost/callback"],
    ["http://localhost.evil.example/callback"], ["http://user@localhost/callback"],
    [], "https://claude.ai/api/mcp/auth_callback",
])
def test_registration_refuses_other_redirect_uris(client, uris):
    r = register(client, uris)
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_redirect_uri"


def test_registration_refuses_unsupported_grants_and_scopes(client):
    assert register(client, grant_types=["client_credentials"]).json()["error"] == \
        "invalid_client_metadata"
    assert register(client, scope="admin").json()["error"] == "invalid_client_metadata"


def test_secret_based_auth_request_is_registered_as_a_public_client(client):
    r = register(client, token_endpoint_auth_method="client_secret_post")
    assert r.status_code == 201
    assert r.json()["token_endpoint_auth_method"] == "none"
    assert "client_secret" not in r.json()


# ---------------------------------------------------------------------------
# Authorization endpoint
# ---------------------------------------------------------------------------


def test_authorize_sends_the_browser_to_the_consent_page(client):
    client_id = register(client).json()["client_id"]
    _, challenge = pkce()
    r = authorize(client, client_id, challenge)
    assert r.status_code == 302
    location = r.headers["location"]
    assert location.startswith(f"{settings.frontend_url.rstrip('/')}/oauth/consent/?request=")
    assert "code=" not in location


def test_unknown_client_or_unregistered_redirect_is_not_redirected(client):
    _, challenge = pkce()
    r = authorize(client, "lpc_nope", challenge)
    assert r.status_code == 400 and "location" not in r.headers
    client_id = register(client).json()["client_id"]
    r = authorize(client, client_id, challenge, redirect_uri="https://evil.example/cb")
    assert r.status_code == 400 and "location" not in r.headers
    assert r.json()["error"] == "invalid_request"


def test_missing_pkce_is_redirected_back_with_error_state_and_iss(client):
    client_id = register(client).json()["client_id"]
    r = authorize(client, client_id, "", code_challenge_method="plain")
    assert r.status_code == 302
    q = query(r.headers["location"])
    assert r.headers["location"].startswith(CLAUDE)
    assert q["error"] == "invalid_request" and q["state"] == "st-1" and q["iss"] == ISSUER


def test_wrong_resource_and_unknown_scope_are_refused(client):
    client_id = register(client).json()["client_id"]
    _, challenge = pkce()
    q = query(authorize(client, client_id, challenge,
                        resource="https://other.example/mcp").headers["location"])
    assert q["error"] == "invalid_target"
    q = query(authorize(client, client_id, challenge, scope="leadpilot:admin")
              .headers["location"])
    assert q["error"] == "invalid_scope"


def test_loopback_redirect_port_is_ignored(client):
    client_id = register(client, ["http://localhost:1111/callback"]).json()["client_id"]
    verifier, challenge = pkce()
    r = authorize(client, client_id, challenge, redirect_uri="http://localhost:2222/callback")
    assert r.status_code == 302
    target = approve(client, r.headers["location"])
    assert target.startswith("http://localhost:2222/callback?")
    code = query(target)["code"]
    tokens = exchange(client, client_id, code, verifier,
                      redirect_uri="http://localhost:2222/callback")
    assert tokens.status_code == 200


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


def test_consent_page_shows_redirect_host_and_scopes(client):
    client_id = register(client).json()["client_id"]
    _, challenge = pkce()
    location = authorize(client, client_id, challenge).headers["location"]
    r = client.get(f"/oauth/requests/{query(location)['request']}")
    assert r.status_code == 200
    body = r.json()
    assert body["redirect_host"] == "claude.ai"
    assert body["client_name"] == "Claude"
    assert [s["scope"] for s in body["scopes"]] == ["leadpilot:read", "leadpilot:write",
                                                    "offline_access"]
    assert all(s["description"] for s in body["scopes"])


def test_consent_requires_a_signed_in_person(client):
    client_id = register(client).json()["client_id"]
    _, challenge = pkce()
    request_id = query(authorize(client, client_id, challenge).headers["location"])["request"]
    r = client.get(f"/oauth/requests/{request_id}", headers={"Authorization": ""})
    assert r.status_code == 401


def test_consent_refuses_a_personal_api_key(client, db_session, test_user):
    from app.services import api_keys

    _row, key = api_keys.create(db_session, test_user.id, "script")
    client_id = register(client).json()["client_id"]
    _, challenge = pkce()
    request_id = query(authorize(client, client_id, challenge).headers["location"])["request"]
    r = client.post(f"/oauth/requests/{request_id}/decision", json={"approve": True},
                    headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 403


def test_denied_consent_returns_access_denied(client):
    client_id = register(client).json()["client_id"]
    _, challenge = pkce()
    target = approve(client, authorize(client, client_id, challenge).headers["location"],
                     approve=False)
    q = query(target)
    assert q["error"] == "access_denied" and q["state"] == "st-1" and q["iss"] == ISSUER
    assert "code" not in q


def test_a_request_is_answered_once(client):
    client_id = register(client).json()["client_id"]
    _, challenge = pkce()
    location = authorize(client, client_id, challenge).headers["location"]
    approve(client, location)
    r = client.post(f"/oauth/requests/{query(location)['request']}/decision",
                    json={"approve": True})
    assert r.status_code == 409


def test_an_expired_request_is_refused(client, db_session):
    from datetime import datetime, timedelta, timezone

    from app.db.models import OAuthAuthorizationCode

    client_id = register(client).json()["client_id"]
    _, challenge = pkce()
    request_id = query(authorize(client, client_id, challenge).headers["location"])["request"]
    row = db_session.get(OAuthAuthorizationCode, __import__("uuid").UUID(request_id))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert client.get(f"/oauth/requests/{request_id}").status_code == 410


# ---------------------------------------------------------------------------
# Token endpoint: the full code -> token -> refresh -> rotate -> reuse flow
# ---------------------------------------------------------------------------


def test_full_flow_code_token_refresh_rotate_reuse_rejected(client, world):
    client_id, first = connect(client)
    assert first["token_type"] == "Bearer"
    assert first["scope"] == "leadpilot:read leadpilot:write offline_access"
    assert first["refresh_token"] and first["expires_in"] == settings.mcp_access_ttl_seconds

    r = mcp_call(client, first["access_token"])
    assert r.status_code == 200 and r.json()["result"]["structuredContent"]["total"] == 3

    r = refresh(client, client_id, first["refresh_token"])
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert mcp_call(client, second["access_token"]).status_code == 200

    # The rotated refresh token again: invalid_grant, and the family is gone.
    reuse = refresh(client, client_id, first["refresh_token"])
    assert reuse.status_code == 400 and reuse.json()["error"] == "invalid_grant"
    assert mcp_call(client, second["access_token"]).status_code == 401
    dead = refresh(client, client_id, second["refresh_token"])
    assert dead.status_code == 400 and dead.json()["error"] == "invalid_grant"


def test_pkce_mismatch_is_rejected(client):
    client_id = register(client).json()["client_id"]
    _, challenge = pkce()
    code = query(approve(client, authorize(client, client_id, challenge)
                         .headers["location"]))["code"]
    wrong_verifier, _ = pkce()
    r = exchange(client, client_id, code, wrong_verifier)
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


def test_wrong_redirect_uri_at_the_token_endpoint_is_rejected(client):
    client_id = register(client, [CLAUDE, CHATGPT]).json()["client_id"]
    verifier, challenge = pkce()
    code = query(approve(client, authorize(client, client_id, challenge)
                         .headers["location"]))["code"]
    r = exchange(client, client_id, code, verifier, redirect_uri=CHATGPT)
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"


def test_code_for_another_client_is_rejected(client):
    client_id = register(client).json()["client_id"]
    other = register(client).json()["client_id"]
    verifier, challenge = pkce()
    code = query(approve(client, authorize(client, client_id, challenge)
                         .headers["location"]))["code"]
    assert exchange(client, other, code, verifier).json()["error"] == "invalid_grant"
    assert exchange(client, "lpc_unknown", code, verifier).status_code == 401


def test_code_reuse_is_rejected_and_revokes_the_first_session(client, world):
    client_id = register(client).json()["client_id"]
    verifier, challenge = pkce()
    code = query(approve(client, authorize(client, client_id, challenge)
                         .headers["location"]))["code"]
    first = exchange(client, client_id, code, verifier).json()
    again = exchange(client, client_id, code, verifier)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"
    assert mcp_call(client, first["access_token"]).status_code == 401


def test_no_refresh_token_without_offline_access(client, world):
    _client_id, tokens = connect(client, scope="leadpilot:read")
    assert "refresh_token" not in tokens
    assert tokens["scope"] == "leadpilot:read"


def test_refresh_cannot_widen_scope(client, world):
    client_id, tokens = connect(client, scope="leadpilot:read offline_access")
    r = client.post("/oauth/token", headers=FORM, data={
        "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"],
        "client_id": client_id, "scope": "leadpilot:read leadpilot:write"})
    assert r.json()["error"] == "invalid_scope"
    # ...and the refusal left the session working.
    assert refresh(client, client_id, tokens["refresh_token"]).status_code == 200


def test_refresh_token_for_another_client_is_rejected(client, world):
    _client_id, tokens = connect(client)
    other = register(client).json()["client_id"]
    r = refresh(client, other, tokens["refresh_token"])
    assert r.json()["error"] == "invalid_grant"


def test_unsupported_grant_and_missing_fields(client):
    r = client.post("/oauth/token", headers=FORM, data={"grant_type": "client_credentials"})
    assert r.json()["error"] == "unsupported_grant_type"
    r = client.post("/oauth/token", headers=FORM, data={"grant_type": "authorization_code"})
    assert r.json()["error"] == "invalid_request"


def test_suspended_account_cannot_refresh(client, world, db_session):
    client_id, tokens = connect(client)
    world.me.is_suspended = True
    db_session.commit()
    r = refresh(client, client_id, tokens["refresh_token"])
    assert r.json()["error"] == "invalid_grant"
    assert mcp_call(client, tokens["access_token"]).status_code == 401


# ---------------------------------------------------------------------------
# Token separation, revocation, tenancy
# ---------------------------------------------------------------------------


def test_connector_refresh_token_is_refused_by_the_web_refresh(client, world):
    _client_id, tokens = connect(client)
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


def test_web_refresh_token_is_refused_by_the_token_endpoint(client, world, db_session):
    from app.services import auth_sessions

    web = auth_sessions.issue_session_tokens(db_session, world.me)
    client_id = register(client).json()["client_id"]
    r = refresh(client, client_id, web.refresh_token)
    assert r.json()["error"] == "invalid_grant"


def test_revocation_ends_the_connection(client, world):
    client_id, tokens = connect(client)
    r = client.post("/oauth/revoke", headers=FORM,
                    data={"token": tokens["refresh_token"], "client_id": client_id})
    assert r.status_code == 200
    assert mcp_call(client, tokens["access_token"]).status_code == 401
    assert refresh(client, client_id, tokens["refresh_token"]).json()["error"] == \
        "invalid_grant"


def test_revocation_also_stops_access_tokens_of_already_rotated_sessions(client, world):
    # The first access token's session row is ROTATED after a refresh; the
    # family revocation leaves that row as it was, so only the family-wide
    # check in connector_session_live can stop it.
    client_id, first = connect(client)
    second = refresh(client, client_id, first["refresh_token"]).json()
    assert mcp_call(client, first["access_token"]).status_code == 200   # still in its hour
    client.post("/oauth/revoke", headers=FORM,
                data={"token": second["refresh_token"], "client_id": client_id})
    assert mcp_call(client, first["access_token"]).status_code == 401
    assert mcp_call(client, second["access_token"]).status_code == 401


def test_password_change_signs_the_connector_out(client, world, db_session):
    from datetime import datetime, timedelta, timezone

    client_id, tokens = connect(client)
    world.me.password_changed_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    db_session.commit()
    assert mcp_call(client, tokens["access_token"]).status_code == 401
    assert refresh(client, client_id, tokens["refresh_token"]).json()["error"] == \
        "invalid_grant"


def test_a_token_from_one_tenant_returns_nothing_of_another(client, world):
    _client_id, tokens = connect(client)
    theirs = world.theirs
    r = mcp_call(client, tokens["access_token"], "get_lead", {"lead_id": str(theirs.leads[0].id)})
    result = r.json()["result"]
    assert result["isError"] is True
    assert "lead not found" in result["content"][0]["text"]
    listing = mcp_call(client, tokens["access_token"]).json()["result"]["structuredContent"]
    their_ids = {str(lead.id) for lead in theirs.leads}
    assert not their_ids & {item["id"] for item in listing["items"]}


def test_consent_audit_rows_name_the_client_not_the_code(client, world, db_session):
    from sqlalchemy import select

    from app.db.models import SecurityAuditEvent

    client_id, _tokens = connect(client)
    rows = db_session.execute(select(SecurityAuditEvent).where(
        SecurityAuditEvent.action == "oauth.consent_granted")).scalars().all()
    assert len(rows) == 1
    assert rows[0].details_json["oauth_client_id"] == client_id
    assert "code" not in rows[0].details_json
