"""The Claude / ChatGPT connector against REAL PostgreSQL.

tests/mcp/ proves the behaviour on SQLite. This runs the whole path on the
dialect that ships: migration 0091's tables (UUID, timestamptz, JSON),
the atomic UPDATE ... WHERE claims for codes and refresh tokens, the family
revocation query, and the tenant-scoped tool queries -- through the real
FastAPI app with its lifespan (the MCP server is built there) and the real
OAuth endpoints, exactly as Claude drives them.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import models as m
from app.services import auth as auth_svc

CLAUDE = "https://claude.ai/api/mcp/auth_callback"
RESOURCE = "http://testserver/mcp"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
MCP = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
       "MCP-Protocol-Version": "2025-11-25"}


def _account(db, tag):
    user = m.User(email=f"mcp-pg-{tag}-{uuid.uuid4().hex[:6]}@example.test",
                  email_verified=True)
    db.add(user)
    db.flush()
    product = m.Product(user_id=user.id, name=f"Product {tag}", description="d",
                        type=m.ProductType.SKILL)
    db.add(product)
    db.flush()
    strategy = m.Strategy(product_id=product.id, flow_type=m.FlowType.NO_CLIENTS)
    db.add(strategy)
    db.flush()
    lead = m.Lead(strategy_id=strategy.id, source="apollo", external_id=uuid.uuid4().hex,
                  full_name=f"Prospect {tag}", company=f"Co {tag}",
                  email=f"prospect-{tag}@example.test", status=m.LeadStatus.VERIFIED,
                  fpta_overall=77, enrichment_json={"k": tag})
    db.add(lead)
    db.commit()
    return user, product, strategy, lead


@pytest.fixture()
def app_client(pg_engine, db_session, monkeypatch):
    from app.db.base import get_db
    from app.main import app
    from app.mcp import context as mcp_context
    from app.workers import tasks as worker_tasks

    monkeypatch.setattr(settings, "mcp_enabled", True)
    monkeypatch.setattr(settings, "mcp_resource_url", RESOURCE)
    monkeypatch.setattr(mcp_context, "session_factory",
                        sessionmaker(bind=pg_engine, expire_on_commit=False))
    enqueued: list[str] = []
    monkeypatch.setattr(worker_tasks.run_pipeline, "delay", enqueued.append, raising=False)
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            client.enqueued = enqueued
            yield client
    finally:
        app.dependency_overrides.clear()


def _connect(client, user, scope="leadpilot:read leadpilot:write offline_access"):
    client_id = client.post("/oauth/register", json={"redirect_uris": [CLAUDE]}).json()[
        "client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    r = client.get("/oauth/authorize", follow_redirects=False, params={
        "response_type": "code", "client_id": client_id, "redirect_uri": CLAUDE,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "s",
        "scope": scope, "resource": RESOURCE})
    assert r.status_code == 302, r.text
    request_id = parse_qs(urlsplit(r.headers["location"]).query)["request"][0]
    web = {"Authorization": f"Bearer {auth_svc.issue_tokens(user.id)['access_token']}"}
    target = client.post(f"/oauth/requests/{request_id}/decision", json={"approve": True},
                         headers=web).json()["redirect_to"]
    code = parse_qs(urlsplit(target).query)["code"][0]
    tokens = client.post("/oauth/token", headers=FORM, data={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": CLAUDE, "client_id": client_id})
    assert tokens.status_code == 200, tokens.text
    return client_id, tokens.json()


def _tool(client, token, name, arguments=None):
    r = client.post("/mcp", headers={**MCP, "Authorization": f"Bearer {token}"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": name, "arguments": arguments or {}}})
    return r


def test_full_connector_flow_on_postgres(app_client, db_session):
    alice, a_product, a_strategy, a_lead = _account(db_session, "alice")
    _bob, _b_product, b_strategy, b_lead = _account(db_session, "bob")
    client_id, first = _connect(app_client, alice)

    listing = _tool(app_client, first["access_token"], "list_leads").json()["result"]
    assert listing["structuredContent"]["total"] == 1
    assert listing["structuredContent"]["items"][0]["id"] == str(a_lead.id)
    lead = _tool(app_client, first["access_token"], "get_lead",
                 {"lead_id": str(a_lead.id)}).json()["result"]["structuredContent"]
    assert lead["fpta"]["overall"] == 77
    assert lead["untrusted_content"]["enrichment"] == {"k": "alice"}

    # Another tenant's ids: not found, nothing leaks.
    cross = _tool(app_client, first["access_token"], "get_lead",
                  {"lead_id": str(b_lead.id)}).json()["result"]
    assert cross["isError"] is True and "lead not found" in cross["content"][0]["text"]
    paused = _tool(app_client, first["access_token"], "pause_campaign",
                   {"strategy_id": str(b_strategy.id)}).json()["result"]
    assert paused["isError"] is True

    # Writes through the real services.
    ok = _tool(app_client, first["access_token"], "pause_campaign",
               {"strategy_id": str(a_strategy.id)}).json()["result"]
    assert ok["structuredContent"]["campaign_state"] == "paused_manual"
    created = _tool(app_client, first["access_token"], "create_strategy",
                    {"product_id": str(a_product.id), "max_budget_usd": 5}).json()["result"]
    assert created["isError"] is False, created
    assert app_client.enqueued == [created["structuredContent"]["id"]]
    db_session.expire_all()
    assert db_session.get(m.Strategy, b_strategy.id).campaign_state == "active"
    actions = db_session.execute(select(m.SecurityAuditEvent.action, m.SecurityAuditEvent.details_json)
                                 .where(m.SecurityAuditEvent.action.like("mcp.%"))).all()
    assert {a for a, _ in actions} == {"mcp.pause_campaign", "mcp.create_strategy"}
    assert all(d["actor_channel"] == "mcp" and d["oauth_client_id"] == client_id
               for _, d in actions)

    # Refresh rotation, then reuse: invalid_grant and the family is revoked.
    second = app_client.post("/oauth/token", headers=FORM, data={
        "grant_type": "refresh_token", "refresh_token": first["refresh_token"],
        "client_id": client_id}).json()
    assert _tool(app_client, second["access_token"], "list_strategies").status_code == 200
    reuse = app_client.post("/oauth/token", headers=FORM, data={
        "grant_type": "refresh_token", "refresh_token": first["refresh_token"],
        "client_id": client_id})
    assert reuse.status_code == 400 and reuse.json()["error"] == "invalid_grant"
    assert _tool(app_client, second["access_token"], "list_strategies").status_code == 401
    assert _tool(app_client, first["access_token"], "list_strategies").status_code == 401


def test_code_cannot_be_redeemed_twice_on_postgres(app_client, db_session):
    alice, *_ = _account(db_session, "carol")
    client_id = app_client.post("/oauth/register", json={"redirect_uris": [CLAUDE]}).json()[
        "client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    r = app_client.get("/oauth/authorize", follow_redirects=False, params={
        "response_type": "code", "client_id": client_id, "redirect_uri": CLAUDE,
        "code_challenge": challenge, "code_challenge_method": "S256"})
    request_id = parse_qs(urlsplit(r.headers["location"]).query)["request"][0]
    web = {"Authorization": f"Bearer {auth_svc.issue_tokens(alice.id)['access_token']}"}
    target = app_client.post(f"/oauth/requests/{request_id}/decision", json={"approve": True},
                             headers=web).json()["redirect_to"]
    code = parse_qs(urlsplit(target).query)["code"][0]
    form = {"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
            "redirect_uri": CLAUDE, "client_id": client_id}
    first = app_client.post("/oauth/token", headers=FORM, data=form)
    assert first.status_code == 200
    # No scope requested: the default grant is read + staying connected.
    assert first.json()["scope"] == "leadpilot:read offline_access"
    second = app_client.post("/oauth/token", headers=FORM, data=form)
    assert second.json()["error"] == "invalid_grant"
    assert _tool(app_client, first.json()["access_token"], "list_leads").status_code == 401
