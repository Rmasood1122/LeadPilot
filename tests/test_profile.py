"""Profile: display name and password change.

The password change must (1) prove knowledge of the current password, (2) end
every session so a stolen refresh token dies with the old password, (3) never
leak anything about the hash, and (4) be rate limited.
"""

from __future__ import annotations

from app.db import models as m
from app.services import auth as auth_svc
from app.services import auth_sessions


def _set_password(db, user, pw="old-password-1"):
    user.password_hash = auth_svc.hash_password(pw)
    db.commit()


class TestName:
    def test_me_includes_full_name_null_by_default(self, client):
        assert client.get("/auth/me").json()["full_name"] is None

    def test_set_and_read_back(self, client):
        r = client.patch("/auth/me", json={"full_name": "  Rehan Masood "})
        assert r.status_code == 200
        assert r.json()["full_name"] == "Rehan Masood"
        assert client.get("/auth/me").json()["full_name"] == "Rehan Masood"

    def test_blank_clears_it(self, client):
        client.patch("/auth/me", json={"full_name": "A"})
        assert client.patch("/auth/me", json={"full_name": "   "}).json()["full_name"] is None

    def test_too_long_is_rejected(self, client):
        assert client.patch("/auth/me", json={"full_name": "x" * 121}).status_code == 422

    def test_control_characters_are_rejected(self, client):
        assert client.patch("/auth/me", json={"full_name": "A\x00B"}).status_code == 422

    def test_cannot_change_email_plan_or_admin_through_it(self, client, db_session, test_user):
        r = client.patch("/auth/me", json={"full_name": "A", "plan": "enterprise",
                                           "is_admin": True, "email": "x@y.z"})
        assert r.status_code == 200
        db_session.refresh(test_user)
        assert test_user.plan == m.PlanTier.FREE
        assert test_user.is_admin is False
        assert test_user.email == "test@leadpilot.dev"


class TestChangePassword:
    def _post(self, client, cur="old-password-1", new="new-password-2"):
        return client.post("/auth/change-password",
                           json={"current_password": cur, "new_password": new})

    def test_success_changes_the_hash(self, client, db_session, test_user):
        _set_password(db_session, test_user)
        r = self._post(client)
        assert r.status_code == 200
        db_session.refresh(test_user)
        assert auth_svc.verify_password("new-password-2", test_user.password_hash)
        assert not auth_svc.verify_password("old-password-1", test_user.password_hash)

    def test_wrong_current_password_is_400_and_changes_nothing(self, client, db_session, test_user):
        _set_password(db_session, test_user)
        before = test_user.password_hash
        assert self._post(client, cur="not-it-at-all").status_code == 400
        db_session.refresh(test_user)
        assert test_user.password_hash == before

    def test_short_new_password_is_rejected(self, client, db_session, test_user):
        _set_password(db_session, test_user)
        assert self._post(client, new="short").status_code == 422

    def test_same_password_is_rejected(self, client, db_session, test_user):
        _set_password(db_session, test_user)
        assert self._post(client, new="old-password-1").status_code == 400

    def test_account_without_a_password_cannot_use_it(self, client):
        assert self._post(client).status_code == 400

    def test_every_session_is_revoked(self, client, db_session, test_user):
        _set_password(db_session, test_user)
        auth_sessions.issue_session_tokens(db_session, test_user)
        auth_sessions.issue_session_tokens(db_session, test_user)
        assert self._post(client).status_code == 200
        rows = db_session.query(m.AuthSession).filter_by(user_id=test_user.id).all()
        assert rows and all(r.revoked_at is not None for r in rows)

    def test_other_accounts_sessions_are_untouched(self, client, db_session, test_user):
        _set_password(db_session, test_user)
        other = m.User(email="other@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        auth_sessions.issue_session_tokens(db_session, other)
        assert self._post(client).status_code == 200
        rows = db_session.query(m.AuthSession).filter_by(user_id=other.id).all()
        assert rows and all(r.revoked_at is None for r in rows)

    def test_response_never_contains_a_hash(self, client, db_session, test_user):
        _set_password(db_session, test_user)
        assert "pbkdf2" not in self._post(client).text

    def test_audited_without_the_password(self, client, db_session, test_user):
        _set_password(db_session, test_user)
        self._post(client)
        ev = db_session.query(m.SecurityAuditEvent).filter_by(
            action="auth.password_changed", user_id=test_user.id).one()
        assert "password" not in str(ev.details_json).lower()

    def test_wrong_attempts_are_rate_limited(self, client, db_session, test_user):
        _set_password(db_session, test_user)
        codes = [self._post(client, cur="wrong-password").status_code for _ in range(40)]
        assert 429 in codes
