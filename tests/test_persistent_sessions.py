"""Persistent sign-in and post-login plan status (migration 0052).

What must hold:
  * the web client's refresh token is an HttpOnly cookie, never a readable
    body field, and "keep me signed in" decides whether it outlives the
    browser session;
  * the cookie is only read alongside X-Auth-Transport (the CSRF guard);
  * refresh rotates, a replayed token revokes its whole family, logout
    revokes for real;
  * the body transport the native app, SDK and CLI use is unchanged, and
    tokens issued before sessions existed keep working;
  * every sign-in, refresh and /auth/me says whether the account has a plan.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select

from app.config import Settings, settings
from app.db import models as m
from app.services import auth as auth_svc
from app.services import security_audit

PASSWORD = "CorrectHorse!1"
EMAIL = "persist@example.com"
COOKIE = settings.auth_refresh_cookie_name
WEB = {"X-Auth-Transport": "cookie"}


@pytest.fixture(scope="module")
def password_hash():
    # 600k PBKDF2 iterations: hash once for the module, not once per test.
    return auth_svc.hash_password(PASSWORD)


@pytest.fixture()
def account(db_session, password_hash):
    user = m.User(email=EMAIL, password_hash=password_hash, email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, *, remember=True, web=True):
    client.cookies.clear()
    resp = client.post("/auth/login",
                       json={"email": EMAIL, "password": PASSWORD, "remember_me": remember},
                       headers=WEB if web else {})
    assert resp.status_code == 200, resp.text
    return resp


def _set_cookie(resp) -> str | None:
    values = [v for v in resp.headers.get_list("set-cookie") if v.startswith(f"{COOKIE}=")]
    assert len(values) <= 1, values
    return values[0] if values else None


def _cookie_value(resp) -> str:
    header = _set_cookie(resp)
    assert header, "no refresh cookie was set"
    return header.split(";", 1)[0].split("=", 1)[1]


def _refresh_with_cookie(client, token, *, header=True):
    client.cookies.clear()
    headers = {"Cookie": f"{COOKIE}={token}"}
    if header:
        headers.update(WEB)
    return client.post("/auth/refresh", headers=headers)


def _sessions(db_session, user):
    db_session.expire_all()
    return db_session.execute(
        select(m.AuthSession).where(m.AuthSession.user_id == user.id)
        .order_by(m.AuthSession.created_at)).scalars().all()


def _session_for(db_session, token) -> m.AuthSession:
    jti = jwt.decode(token, options={"verify_signature": False})["jti"]
    db_session.expire_all()
    return db_session.get(m.AuthSession, __import__("uuid").UUID(jti))


class TestWebCookieTransport:
    def test_login_sets_an_httponly_cookie_and_keeps_the_token_out_of_the_body(
            self, client, account):
        resp = _login(client)
        body = resp.json()
        assert "refresh_token" not in body
        assert body["access_token"]
        header = _set_cookie(resp).lower()
        assert "httponly" in header
        assert "path=/auth" in header
        assert "samesite=lax" in header
        assert f"max-age={settings.jwt_refresh_ttl_seconds}" in header
        assert body["session_persistent"] is True

    def test_unticked_keep_me_signed_in_is_a_browser_session_cookie(
            self, client, db_session, account):
        resp = _login(client, remember=False)
        header = _set_cookie(resp).lower()
        assert "max-age" not in header and "expires" not in header
        row = _session_for(db_session, _cookie_value(resp))
        assert row.persistent is False
        lifetime = row.expires_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
        assert lifetime <= timedelta(seconds=settings.auth_ephemeral_session_ttl_seconds)

    def test_cookie_refresh_rotates_the_token(self, client, db_session, account):
        first = _cookie_value(_login(client))
        resp = _refresh_with_cookie(client, first)
        assert resp.status_code == 200, resp.text
        assert "refresh_token" not in resp.json()
        assert resp.json()["user"]["email"] == EMAIL
        second = _cookie_value(resp)
        assert second != first
        old, new = _session_for(db_session, first), _session_for(db_session, second)
        assert old.revoked_reason == "rotated" and old.replaced_by_id == new.id
        assert new.family_id == old.family_id and new.revoked_at is None

    def test_cookie_is_ignored_without_the_transport_header(self, client, db_session, account):
        """The CSRF guard: a cross-site form post carries the cookie but
        cannot carry a custom header."""
        token = _cookie_value(_login(client))
        resp = _refresh_with_cookie(client, token, header=False)
        assert resp.status_code == 401
        assert _session_for(db_session, token).revoked_at is None

    def test_a_failed_cookie_refresh_clears_the_cookie(self, client, account):
        resp = _refresh_with_cookie(client, "not-a-token")
        assert resp.status_code == 401
        assert "max-age=0" in (_set_cookie(resp) or "").lower()

    def test_restore_with_no_cookie_is_a_plain_401(self, client):
        client.cookies.clear()
        resp = client.post("/auth/refresh", headers=WEB)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "missing refresh token"

    def test_logout_revokes_the_session_and_clears_the_cookie(
            self, client, db_session, account):
        token = _cookie_value(_login(client))
        client.cookies.clear()
        out = client.post("/auth/logout", headers={**WEB, "Cookie": f"{COOKIE}={token}"})
        assert out.status_code == 204
        assert "max-age=0" in (_set_cookie(out) or "").lower()
        assert all(s.revoked_reason == "logout" for s in _sessions(db_session, account))
        assert _refresh_with_cookie(client, token).status_code == 401
        actions = db_session.execute(select(m.SecurityAuditEvent.action)).scalars().all()
        assert security_audit.AUTH_LOGOUT in actions

    def test_logout_without_a_session_still_succeeds(self, client):
        client.cookies.clear()
        assert client.post("/auth/logout", headers=WEB).status_code == 204


class TestRotationSecurity:
    def test_a_concurrent_refresh_inside_the_grace_window_gets_an_access_token(
            self, client, db_session, account):
        first = _cookie_value(_login(client))
        second = _cookie_value(_refresh_with_cookie(client, first))
        late = _refresh_with_cookie(client, first)
        assert late.status_code == 200
        assert late.json()["access_token"]
        assert _set_cookie(late) is None, "the winner's cookie must not be overwritten"
        assert _refresh_with_cookie(client, second).status_code == 200

    def test_replaying_a_rotated_token_revokes_the_whole_family(
            self, client, db_session, account):
        first = _cookie_value(_login(client))
        second = _cookie_value(_refresh_with_cookie(client, first))
        old = _session_for(db_session, first)
        old.rotated_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db_session.commit()

        replay = _refresh_with_cookie(client, first)
        assert replay.status_code == 401
        assert _refresh_with_cookie(client, second).status_code == 401, \
            "the legitimate holder's newer token must die too"
        assert {s.revoked_reason for s in _sessions(db_session, account)} <= {
            "rotated", "reuse_detected"}
        actions = db_session.execute(select(m.SecurityAuditEvent.action)).scalars().all()
        assert security_audit.AUTH_REFRESH_REUSE in actions

    def test_an_expired_session_is_refused(self, client, db_session, account):
        token = _cookie_value(_login(client))
        row = _session_for(db_session, token)
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()
        resp = _refresh_with_cookie(client, token)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "session expired"

    def test_an_access_token_is_not_a_refresh_token(self, client, account):
        access = _login(client).json()["access_token"]
        assert _refresh_with_cookie(client, access).status_code == 401


class TestBodyTransportCompatibility:
    def test_native_and_sdk_clients_keep_the_body_transport(self, client, account):
        resp = _login(client, web=False)
        assert _set_cookie(resp) is None
        refresh = resp.json()["refresh_token"]
        rotated = client.post("/auth/refresh", json={"refresh_token": refresh})
        assert rotated.status_code == 200
        assert rotated.json()["refresh_token"] != refresh
        assert _set_cookie(rotated) is None

    def test_body_logout_revokes(self, client, db_session, account):
        refresh = _login(client, web=False).json()["refresh_token"]
        assert client.post("/auth/logout", json={"refresh_token": refresh}).status_code == 204
        assert client.post("/auth/refresh",
                           json={"refresh_token": refresh}).status_code == 401

    def test_a_pre_session_refresh_token_is_exchanged_for_a_tracked_one(
            self, client, db_session, account):
        legacy = auth_svc.issue_tokens(account.id)["refresh_token"]
        resp = client.post("/auth/refresh", json={"refresh_token": legacy})
        assert resp.status_code == 200, resp.text
        claims = jwt.decode(resp.json()["refresh_token"], options={"verify_signature": False})
        assert claims["jti"] and claims["fam"]
        assert len(_sessions(db_session, account)) == 1

    def test_pre_session_tokens_are_refused_once_switched_off(
            self, client, account, monkeypatch):
        monkeypatch.setattr(settings, "auth_accept_legacy_refresh_tokens", False)
        legacy = auth_svc.issue_tokens(account.id)["refresh_token"]
        assert client.post("/auth/refresh",
                           json={"refresh_token": legacy}).status_code == 401


class TestCookieConfiguration:
    def test_sessions_last_thirty_days_by_default(self):
        assert Settings.model_fields["jwt_refresh_ttl_seconds"].default == 30 * 24 * 3600

    def test_secure_flag_follows_the_environment(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_refresh_cookie_secure", None)
        monkeypatch.setattr(settings, "auth_refresh_cookie_samesite", "lax")
        monkeypatch.setattr(settings, "app_env", "development")
        assert settings.refresh_cookie_secure is False
        monkeypatch.setattr(settings, "app_env", "production")
        assert settings.refresh_cookie_secure is True

    def test_samesite_none_always_forces_secure(self, monkeypatch):
        monkeypatch.setattr(settings, "app_env", "development")
        monkeypatch.setattr(settings, "auth_refresh_cookie_secure", False)
        monkeypatch.setattr(settings, "auth_refresh_cookie_samesite", "None")
        assert settings.refresh_cookie_samesite == "none"
        assert settings.refresh_cookie_secure is True


class TestPlanStatusOnSignIn:
    def _user(self, client, **headers):
        resp = _login(client)
        me = client.get("/auth/me",
                        headers={"Authorization": f"Bearer {resp.json()['access_token']}"})
        assert me.status_code == 200
        assert me.json()["has_active_plan"] == resp.json()["user"]["has_active_plan"]
        return me.json()

    def test_a_new_account_without_a_plan(self, client, account):
        user = self._user(client)
        assert user["has_active_plan"] is False
        assert user["subscription_status"] is None

    @pytest.mark.parametrize("status,expected", [
        ("trialing", True), ("active", True), ("past_due", True),
        ("incomplete", False), ("canceled", False),
    ])
    def test_subscription_status_decides(self, client, db_session, account, status, expected):
        db_session.add(m.BillingSubscription(user_id=account.id, billing_model="monthly",
                                             tier="growth", status=status))
        db_session.commit()
        user = self._user(client)
        assert user["has_active_plan"] is expected
        assert user["subscription_status"] == status

    def test_a_plan_set_without_a_subscription_row_counts(self, client, db_session, account):
        account.plan = m.PlanTier.PRO
        db_session.commit()
        assert self._user(client)["has_active_plan"] is True

    def test_operators_are_never_sent_to_pricing(self, client, db_session, account):
        account.is_admin = True
        db_session.commit()
        assert self._user(client)["has_active_plan"] is True

    def test_a_member_of_a_paying_workspace_has_access(self, client, db_session, account):
        owner = m.User(email="owner@example.com", email_verified=True, plan=m.PlanTier.GROWTH)
        db_session.add(owner)
        db_session.flush()
        workspace = m.Workspace(name="Owner's workspace", slug="owner-ws",
                                owner_user_id=owner.id)
        db_session.add(workspace)
        db_session.flush()
        db_session.add(m.WorkspaceMember(workspace_id=workspace.id, user_id=account.id,
                                         role="manager"))
        db_session.commit()
        assert self._user(client)["has_active_plan"] is True

    def test_session_restore_reports_plan_status(self, client, db_session, account):
        token = _cookie_value(_login(client))
        resp = _refresh_with_cookie(client, token)
        assert resp.json()["user"]["has_active_plan"] is False
