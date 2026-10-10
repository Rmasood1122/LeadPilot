"""P0-D-ENF -- a deployment can close public sign-up, or limit it to its domains.

BEFORE: POST /auth/signup accepted any visitor and no setting turned it off,
so a "single-tenant" deployment (P0-D) was multi-tenant in practice.

NOW: SIGNUP_ENABLED=false refuses every self-registration with 403;
SIGNUP_ALLOWED_EMAIL_DOMAINS limits it to exact domains. Defaults keep the old
behaviour. Refusal happens before any account lookup (no enumeration, no
pre-auth claim), before the VPN provider call, and after the rate limiter.
Existing accounts still log in.

Real requests through the real handler; offline (SQLite, in-process mailbox).
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.api import auth as auth_api
from app.config import Settings, settings
from app.db import models as m
from app.services import auth as auth_svc
from app.services import network_guard

PASSWORD = "hunter22!x"


def _signup(client, email):
    return client.post("/auth/signup", json={"email": email, "password": PASSWORD})


def _user_count(db):
    return db.execute(select(func.count()).select_from(m.User)).scalar_one()


class TestDefaults:
    def test_defaults_keep_signup_open_to_any_domain(self):
        fresh = Settings(_env_file=None)
        assert fresh.signup_enabled is True
        assert fresh.signup_allowed_domains == frozenset()

    def test_default_deployment_still_accepts_signup(self, client, db_session):
        resp = _signup(client, "new@anywhere.example")
        assert resp.status_code == 201, resp.text

    def test_domain_list_is_parsed_leniently(self):
        s = Settings(_env_file=None, signup_allowed_email_domains=" Acme.com, @b.co ,, ")
        assert s.signup_allowed_domains == frozenset({"acme.com", "b.co"})


class TestClosed:
    @pytest.fixture(autouse=True)
    def closed(self, monkeypatch):
        monkeypatch.setattr(settings, "signup_enabled", False)

    def test_new_address_is_refused_and_nothing_is_created(self, client, db_session, mailbox):
        before = _user_count(db_session)
        resp = _signup(client, "stranger@evil.example")
        assert resp.status_code == 403
        assert resp.json()["detail"] == auth_api.SIGNUP_CLOSED_DETAIL
        assert _user_count(db_session) == before
        assert mailbox == []

    def test_existing_address_gets_the_same_answer(self, client, test_user):
        # 403, not the 409 "account already exists": no enumeration.
        resp = _signup(client, test_user.email)
        assert resp.status_code == 403
        assert resp.json()["detail"] == auth_api.SIGNUP_CLOSED_DETAIL

    def test_pre_auth_row_cannot_be_claimed(self, client, db_session):
        row = m.User(email="legacy@acme.example")  # no password: claimable when open
        db_session.add(row)
        db_session.commit()
        resp = _signup(client, "legacy@acme.example")
        assert resp.status_code == 403
        db_session.refresh(row)
        assert row.password_hash is None

    def test_existing_account_still_logs_in(self, client, db_session, test_user):
        test_user.password_hash = auth_svc.hash_password(PASSWORD)
        db_session.commit()
        resp = client.post("/auth/login", json={"email": test_user.email, "password": PASSWORD})
        assert resp.status_code == 200, resp.text

    def test_refused_before_the_vpn_provider_is_asked(self, client, monkeypatch):
        calls = []
        monkeypatch.setattr(network_guard, "enforce_clean_network",
                            lambda *a, **k: calls.append(a))
        assert _signup(client, "x@y.example").status_code == 403
        assert calls == []


class TestDomains:
    @pytest.fixture(autouse=True)
    def acme_only(self, monkeypatch):
        monkeypatch.setattr(settings, "signup_allowed_email_domains", "acme.com, acme.co.uk")

    def test_allowed_domain_registers(self, client):
        assert _signup(client, "Jane@ACME.com").status_code == 201

    def test_second_allowed_domain_registers(self, client):
        assert _signup(client, "bo@acme.co.uk").status_code == 201

    @pytest.mark.parametrize("email", [
        "eve@evil.example",
        "eve@notacme.com",       # suffix match is not enough
        "eve@acme.com.evil.io",  # prefix match is not enough
        "eve@sub.acme.com",      # exact domains only
    ])
    def test_other_domains_are_refused(self, client, db_session, email):
        before = _user_count(db_session)
        resp = _signup(client, email)
        assert resp.status_code == 403
        assert resp.json()["detail"] == auth_api.SIGNUP_DOMAIN_DETAIL
        assert "acme" not in resp.text.lower(), "the allowed domains name the customer"
        assert _user_count(db_session) == before

    def test_closed_wins_over_an_allowed_domain(self, client, monkeypatch):
        monkeypatch.setattr(settings, "signup_enabled", False)
        resp = _signup(client, "jane@acme.com")
        assert resp.status_code == 403
        assert resp.json()["detail"] == auth_api.SIGNUP_CLOSED_DETAIL
