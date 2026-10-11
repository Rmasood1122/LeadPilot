"""P0-3 (audit RF-3) — a suspended account must lose API access everywhere.

Before this fix `get_current_user` (app/services/auth.py, the single auth
chokepoint every protected route resolves through) never looked at
`User.is_suspended`: only `require_admin` did. A suspended user kept full
access to every non-admin route with any token they already held, and could
mint fresh ones through /auth/login and /auth/refresh.

What must hold:
  * a suspended user with a VALID token (access token or personal API key)
    gets 403 "account suspended" — the same status and detail require_admin
    already uses — not 401, because the credentials themselves are fine;
  * an unsuspended user is unaffected;
  * tokens a suspended user obtains through login or refresh are refused
    by protected routes. (Login and refresh themselves still issue tokens —
    they do not go through get_current_user; see the P0-3 report.)
"""

import pytest

from app.db import models as m
from app.services import api_keys
from app.services import auth as auth_svc
from tests.conftest import auth_headers

PASSWORD = "CorrectHorse!1"
EMAIL = "suspended@example.com"
PROTECTED = "/auth/me"


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


def _suspend(db_session, user):
    user.is_suspended = True
    user.suspended_reason = "test"
    db_session.commit()


class TestSuspendedUserIsRefused:
    def test_a_suspended_user_with_a_valid_access_token_gets_403(
            self, anon_client, db_session, account):
        _suspend(db_session, account)
        resp = anon_client.get(PROTECTED, headers=auth_headers(account))
        assert resp.status_code == 403
        assert resp.json()["detail"] == "account suspended"

    def test_a_suspended_user_with_a_valid_api_key_gets_403(
            self, anon_client, db_session, account):
        _row, key = api_keys.create(db_session, account.id, "zapier")
        db_session.commit()
        _suspend(db_session, account)
        resp = anon_client.get(PROTECTED, headers={"X-API-Key": key})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "account suspended"


class TestUnsuspendedUserIsUnaffected:
    def test_an_active_user_still_gets_through(self, anon_client, account):
        resp = anon_client.get(PROTECTED, headers=auth_headers(account))
        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] == EMAIL

    def test_a_resumed_user_gets_access_back(self, anon_client, db_session, account):
        _suspend(db_session, account)
        account.is_suspended = False
        account.suspended_reason = None
        db_session.commit()
        resp = anon_client.get(PROTECTED, headers=auth_headers(account))
        assert resp.status_code == 200, resp.text


class TestLoginAndRefreshWhileSuspended:
    def test_a_token_from_login_is_refused(self, anon_client, db_session, account):
        _suspend(db_session, account)
        login = anon_client.post("/auth/login",
                                 json={"email": EMAIL, "password": PASSWORD})
        assert login.status_code == 200, login.text
        access = login.json()["access_token"]
        resp = anon_client.get(PROTECTED, headers={"Authorization": f"Bearer {access}"})
        assert resp.status_code == 403
        assert resp.json()["detail"] == "account suspended"

    def test_a_token_from_refresh_is_refused(self, anon_client, db_session, account):
        # Signed in while active, suspended afterwards: the refresh token
        # they already hold must not yield a working access token.
        login = anon_client.post("/auth/login",
                                 json={"email": EMAIL, "password": PASSWORD})
        assert login.status_code == 200, login.text
        _suspend(db_session, account)
        rotated = anon_client.post("/auth/refresh",
                                   json={"refresh_token": login.json()["refresh_token"]})
        # Since docs/features/gdpr-erasure.md (review fix 2) the refresh itself
        # is refused -- no new session is created for a suspended account --
        # with the same 403 detail the access-token chokepoint uses.
        assert rotated.status_code == 403, rotated.text
        assert rotated.json()["detail"] == "account suspended"
        assert "access_token" not in rotated.json()
