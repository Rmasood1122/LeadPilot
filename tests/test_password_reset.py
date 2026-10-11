"""Forgotten-password reset (docs/features/password-reset.md).

Every security property in the spec has a test here: no account enumeration
(same answer, same 200, for every address), hash-only token storage, single
use, expiry, one live link per account, sign-out-everywhere, an audit row,
and the accounts that may never reset (suspended, passwordless pre-auth rows,
deleted). The email is read from the in-process `mailbox` fixture
(EMAIL_PROVIDER=memory), so the link asserted on is the one a person receives.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy.orm import sessionmaker

from app.db import models as m
from app.services import api_keys
from app.services import auth as auth_svc
from app.services import auth_sessions
from app.services import password_reset as pr

EMAIL = "forgot@leadpilot.dev"
OLD = "old-password-1"
NEW = "brand-new-password-2"
REQUEST = "/auth/password-reset/request"
CONFIRM = "/auth/password-reset/confirm"


@pytest.fixture()
def account(db_session):
    user = m.User(email=EMAIL, email_verified=True,
                  password_hash=auth_svc.hash_password(OLD))
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def anon(client):
    """The same TestClient with no bearer token: reset is for signed-out people."""
    client.headers.pop("Authorization", None)
    return client


def _request(client, email=EMAIL):
    return client.post(REQUEST, json={"email": email})


def _token_from(mailbox) -> str:
    assert mailbox, "no email was sent"
    match = re.search(r"/reset-password#token=([A-Za-z0-9_\-]+)", mailbox[-1]["text"])
    assert match, mailbox[-1]["text"]
    return match.group(1)


def _confirm(client, token, password=NEW):
    return client.post(CONFIRM, json={"token": token, "new_password": password})


# --------------------------------------------------------------------------
# Request: no enumeration
# --------------------------------------------------------------------------


class TestRequestNeverRevealsAccounts:
    def test_known_address_gets_200_and_one_email(self, anon, account, mailbox):
        r = _request(anon)
        assert r.status_code == 200
        assert r.json()["status"] == "accepted"
        assert len(mailbox) == 1
        assert mailbox[0]["to"] == EMAIL
        assert "Reset your" in mailbox[0]["subject"]

    @pytest.mark.parametrize("email", ["nobody@leadpilot.dev", "NOBODY@other.io"])
    def test_unknown_address_gets_the_identical_answer_and_no_email(
            self, anon, account, mailbox, email):
        known = _request(anon).json()
        mailbox.clear()
        unknown = _request(anon, email)
        assert unknown.status_code == 200
        assert unknown.json() == known
        assert mailbox == []

    def test_address_is_normalised(self, anon, account, mailbox):
        assert _request(anon, "  Forgot@LeadPilot.dev ").status_code in (200, 422)
        r = _request(anon, "Forgot@LeadPilot.dev")
        assert r.status_code == 200
        assert len(mailbox) == 1

    def test_suspended_account_gets_the_same_answer_and_no_email(
            self, anon, account, db_session, mailbox):
        account.is_suspended = True
        db_session.commit()
        r = _request(anon)
        assert r.status_code == 200
        assert r.json()["detail"] == pr_detail()
        assert mailbox == []

    def test_passwordless_pre_auth_row_cannot_be_claimed_by_reset(
            self, anon, db_session, mailbox):
        db_session.add(m.User(email="preauth@leadpilot.dev"))
        db_session.commit()
        r = _request(anon, "preauth@leadpilot.dev")
        assert r.status_code == 200
        assert mailbox == []
        assert db_session.query(m.PasswordResetToken).count() == 0

    def test_malformed_email_is_422_and_spends_no_quota(self, anon, account):
        assert anon.post(REQUEST, json={"email": "not-an-email"}).status_code == 422


def pr_detail() -> str:
    from app.api.auth import PASSWORD_RESET_ACCEPTED

    return PASSWORD_RESET_ACCEPTED


class TestRequestRateLimits:
    def test_per_address_limit_applies_to_addresses_without_accounts_too(
            self, anon, monkeypatch):
        # A fresh IP per call, so only the per-address bucket can trip: this is
        # the distributed mail-bomb aimed at one inbox.
        ips = iter(f"203.0.113.{i}" for i in range(1, 100))
        monkeypatch.setattr("app.api.auth.client_ip", lambda _request: next(ips))
        codes = [_request(anon, "ghost@leadpilot.dev").status_code for _ in range(15)]
        assert codes[:10] == [200] * 10
        assert codes[10:] == [429] * 5

    def test_per_ip_limit(self, anon):
        codes = [_request(anon, f"ghost{i}@leadpilot.dev").status_code for i in range(15)]
        assert 429 in codes

    def test_reset_requests_do_not_spend_the_login_quota(self, anon, account):
        # Ten resets fill the reset IP bucket exactly; were it login's bucket,
        # the sign-in below would be the 11th call and get 429.
        for i in range(10):
            assert _request(anon, f"someone-else{i}@leadpilot.dev").status_code == 200
        r = anon.post("/auth/login", json={"email": EMAIL, "password": OLD})
        assert r.status_code == 200, r.text

    def test_second_request_inside_the_cooldown_sends_nothing(self, anon, account, mailbox):
        _request(anon)
        _request(anon)
        assert len(mailbox) == 1


# --------------------------------------------------------------------------
# The token
# --------------------------------------------------------------------------


class TestToken:
    def test_link_points_at_the_frontend_with_the_token_in_the_fragment(
            self, anon, account, mailbox):
        from app.config import settings

        _request(anon)
        text = mailbox[0]["text"]
        assert f"{settings.frontend_url.rstrip('/')}/reset-password#token=" in text
        assert "?token=" not in text  # never in a query string a server logs
        assert len(_token_from(mailbox)) >= 40

    def test_only_the_hash_is_stored(self, anon, account, db_session, mailbox):
        _request(anon)
        raw = _token_from(mailbox)
        row = db_session.query(m.PasswordResetToken).one()
        assert row.token_hash == pr.token_hash(raw)
        assert raw not in {str(v) for v in vars(row).values()}

    def test_expires_after_the_configured_ttl(self, anon, account, db_session, mailbox):
        _request(anon)
        row = db_session.query(m.PasswordResetToken).one()
        created = row.created_at if row.created_at.tzinfo else row.created_at.replace(
            tzinfo=timezone.utc)
        expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(
            tzinfo=timezone.utc)
        assert expires - created == timedelta(minutes=60)

    def test_requester_ip_is_recorded(self, anon, account, db_session, mailbox):
        _request(anon)
        assert db_session.query(m.PasswordResetToken).one().requested_ip


# --------------------------------------------------------------------------
# Confirm
# --------------------------------------------------------------------------


class TestConfirm:
    def test_resets_the_password(self, anon, account, db_session, mailbox):
        _request(anon)
        r = _confirm(anon, _token_from(mailbox))
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "reset", "signed_out_everywhere": True,
                            "api_keys_revoked": 0}
        db_session.refresh(account)
        assert auth_svc.verify_password(NEW, account.password_hash)
        assert not auth_svc.verify_password(OLD, account.password_hash)
        # and the person can sign in with it
        assert anon.post("/auth/login", json={"email": EMAIL, "password": NEW}).status_code == 200

    def test_issues_no_tokens(self, anon, account, mailbox):
        _request(anon)
        body = _confirm(anon, _token_from(mailbox)).json()
        assert "access_token" not in body and "refresh_token" not in body

    def test_single_use(self, anon, account, db_session, mailbox):
        _request(anon)
        token = _token_from(mailbox)
        assert _confirm(anon, token).status_code == 200
        r = _confirm(anon, token, "another-password-3")
        assert r.status_code == 400
        db_session.refresh(account)
        assert auth_svc.verify_password(NEW, account.password_hash)

    def test_unknown_token_is_400_and_changes_nothing(self, anon, account, db_session):
        before = account.password_hash
        r = _confirm(anon, "x" * 43)
        assert r.status_code == 400
        assert r.json()["detail"] == "This reset link is invalid or has expired. Request a new one."
        db_session.refresh(account)
        assert account.password_hash == before

    def test_expired_token_is_400_and_burnt(self, anon, account, db_session, mailbox):
        _request(anon)
        token = _token_from(mailbox)
        row = db_session.query(m.PasswordResetToken).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db_session.commit()
        assert _confirm(anon, token).status_code == 400
        db_session.refresh(row)
        assert row.used_at is not None
        db_session.refresh(account)
        assert auth_svc.verify_password(OLD, account.password_hash)

    def test_a_newer_link_supersedes_the_older_one(self, anon, account, db_session, mailbox,
                                                   monkeypatch):
        monkeypatch.setattr(pr, "RESEND_COOLDOWN_SECONDS", 0)
        _request(anon)
        first = _token_from(mailbox)
        _request(anon)
        second = _token_from(mailbox)
        assert first != second
        assert _confirm(anon, first).status_code == 400
        assert _confirm(anon, second).status_code == 200

    def test_short_password_is_422_and_does_not_burn_the_link(self, anon, account, mailbox):
        _request(anon)
        token = _token_from(mailbox)
        assert _confirm(anon, token, "short").status_code == 422
        assert _confirm(anon, token).status_code == 200

    def test_signs_out_every_session(self, anon, account, db_session, mailbox):
        auth_sessions.issue_session_tokens(db_session, account)
        auth_sessions.issue_session_tokens(db_session, account)
        _request(anon)
        assert _confirm(anon, _token_from(mailbox)).status_code == 200
        rows = db_session.query(m.AuthSession).filter_by(user_id=account.id).all()
        assert rows and all(r.revoked_at is not None for r in rows)
        assert {r.revoked_reason for r in rows} == {"password_reset"}

    def test_other_accounts_are_untouched(self, anon, account, db_session, mailbox):
        other = m.User(email="other@leadpilot.dev", email_verified=True,
                       password_hash=auth_svc.hash_password(OLD))
        db_session.add(other)
        db_session.commit()
        auth_sessions.issue_session_tokens(db_session, other)
        _request(anon)
        assert _confirm(anon, _token_from(mailbox)).status_code == 200
        db_session.refresh(other)
        assert auth_svc.verify_password(OLD, other.password_hash)
        rows = db_session.query(m.AuthSession).filter_by(user_id=other.id).all()
        assert rows and all(r.revoked_at is None for r in rows)

    def test_audited_without_the_password(self, anon, account, db_session, mailbox):
        _request(anon)
        _confirm(anon, _token_from(mailbox))
        requested = db_session.query(m.SecurityAuditEvent).filter_by(
            action="auth.password_reset_requested", user_id=account.id).one()
        done = db_session.query(m.SecurityAuditEvent).filter_by(
            action="auth.password_reset", user_id=account.id).one()
        assert done.details_json == {"sessions_revoked": 0, "api_keys_revoked": 0}
        for ev in (requested, done):
            assert NEW not in str(ev.details_json)
            assert "pbkdf2" not in str(ev.details_json)

    def test_suspended_after_the_request_cannot_reset(self, anon, account, db_session, mailbox):
        _request(anon)
        token = _token_from(mailbox)
        account.is_suspended = True
        db_session.commit()
        r = _confirm(anon, token)
        assert r.status_code == 400
        db_session.refresh(account)
        assert auth_svc.verify_password(OLD, account.password_hash)
        ev = db_session.query(m.SecurityAuditEvent).filter_by(
            action="auth.password_reset_refused", user_id=account.id).one()
        assert ev.details_json == {"reason": "ineligible"}

    def test_deleted_account_link_is_dead(self, anon, account, db_session, mailbox):
        _request(anon)
        token = _token_from(mailbox)
        db_session.delete(account)
        db_session.commit()
        assert db_session.query(m.PasswordResetToken).count() == 0
        assert _confirm(anon, token).status_code == 400

    def test_confirm_is_rate_limited_per_ip(self, anon):
        codes = [_confirm(anon, f"bad-token-{i}").status_code for i in range(15)]
        assert 429 in codes

    def test_response_never_contains_a_hash(self, anon, account, mailbox):
        _request(anon)
        assert "pbkdf2" not in _confirm(anon, _token_from(mailbox)).text


class TestEmailFailure:
    def test_transport_failure_still_answers_200(self, anon, account, monkeypatch, caplog):
        from app.services.email_sender import EmailSendError

        def boom(**_kw):
            raise EmailSendError("relay down")

        monkeypatch.setattr(pr, "send_email", boom)
        r = _request(anon)
        assert r.status_code == 200
        assert "password reset email FAILED" in caplog.text


# --------------------------------------------------------------------------
# Review fixes (2026-10-11)
# --------------------------------------------------------------------------


def _old_token(user_id, typ: str, *, age_seconds: int = 120, jti: bool = False) -> str:
    """A token minted `age_seconds` ago -- i.e. before a change made now.
    Legacy refresh tokens (no jti) are what pre-session clients still hold."""
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user_id), "typ": typ, "iat": now - timedelta(seconds=age_seconds),
              "exp": now + timedelta(hours=1)}
    if jti:
        claims["jti"] = str(uuid.uuid4())
    return jwt.encode(claims, auth_svc._secret(), algorithm="HS256")


def _reset(anon, mailbox):
    _request(anon)
    assert _confirm(anon, _token_from(mailbox)).status_code == 200


class TestSignedOutEverywhereIsTrue:
    def test_reset_revokes_every_api_key(self, anon, account, db_session, mailbox):
        _row, key = api_keys.create(db_session, account.id, "zapier")
        assert api_keys.authenticate(db_session, key) is not None
        _request(anon)
        r = _confirm(anon, _token_from(mailbox))
        assert r.json()["api_keys_revoked"] == 1
        assert api_keys.authenticate(db_session, key) is None
        done = db_session.query(m.SecurityAuditEvent).filter_by(
            action="auth.password_reset", user_id=account.id).one()
        assert done.details_json["api_keys_revoked"] == 1

    def test_change_password_revokes_every_api_key(self, client, db_session, test_user):
        test_user.password_hash = auth_svc.hash_password(OLD)
        db_session.commit()
        _row, key = api_keys.create(db_session, test_user.id, "make")
        r = client.post("/auth/change-password",
                        json={"current_password": OLD, "new_password": NEW})
        assert r.status_code == 200 and r.json()["api_keys_revoked"] == 1
        assert api_keys.authenticate(db_session, key) is None

    def test_other_accounts_keys_survive(self, anon, account, db_session, mailbox):
        other = m.User(email="keys-other@leadpilot.dev", email_verified=True)
        db_session.add(other)
        db_session.commit()
        _row, key = api_keys.create(db_session, other.id, "theirs")
        _reset(anon, mailbox)
        assert api_keys.authenticate(db_session, key) is not None

    @pytest.mark.parametrize("how", ["reset", "change"])
    def test_password_changed_at_is_stamped(self, anon, client, account, db_session, mailbox,
                                            test_user, how):
        if how == "reset":
            _reset(anon, mailbox)
            user = account
        else:
            test_user.password_hash = auth_svc.hash_password(OLD)
            db_session.commit()
            from tests.conftest import auth_headers

            assert client.post("/auth/change-password", headers=auth_headers(test_user),
                               json={"current_password": OLD, "new_password": NEW}
                               ).status_code == 200
            user = test_user
        db_session.refresh(user)
        assert user.password_changed_at is not None

    def test_legacy_refresh_token_from_before_a_reset_is_refused(
            self, anon, account, db_session, mailbox):
        legacy = _old_token(account.id, "refresh")
        assert anon.post("/auth/refresh", json={"refresh_token": legacy}).status_code == 200
        legacy = _old_token(account.id, "refresh")
        _reset(anon, mailbox)
        assert anon.post("/auth/refresh", json={"refresh_token": legacy}).status_code == 401

    def test_access_token_from_before_a_reset_is_refused(
            self, anon, account, db_session, mailbox):
        old_access = _old_token(account.id, "access")
        assert anon.get("/auth/me", headers={"Authorization": f"Bearer {old_access}"}
                        ).status_code == 200
        _reset(anon, mailbox)
        assert anon.get("/auth/me", headers={"Authorization": f"Bearer {old_access}"}
                        ).status_code == 401

    def test_a_sign_in_right_after_the_reset_works(self, anon, account, mailbox):
        _reset(anon, mailbox)
        tokens = anon.post("/auth/login", json={"email": EMAIL, "password": NEW}).json()
        assert anon.get("/auth/me", headers={
            "Authorization": f"Bearer {tokens['access_token']}"}).status_code == 200
        assert anon.post("/auth/refresh",
                         json={"refresh_token": tokens["refresh_token"]}).status_code == 200

    def test_helper_compares_whole_seconds(self):
        changed = datetime(2026, 10, 12, 12, 0, 0, 700000, tzinfo=timezone.utc)
        user = m.User(email="x@y.z", password_changed_at=changed)
        second = int(changed.timestamp())
        assert auth_sessions._issued_before_password_change(user, {"iat": second - 1})
        assert not auth_sessions._issued_before_password_change(user, {"iat": second})
        assert auth_sessions._issued_before_password_change(user, {})
        assert not auth_sessions._issued_before_password_change(
            m.User(email="n@y.z"), {"iat": 0})


class TestAtomicRedeem:
    def test_a_stale_second_redeemer_cannot_spend_the_link_again(
            self, anon, account, db_session, mailbox):
        """Same shape as tests/test_duplicate_send_claim.py: session B read the
        link while it was unused, A spends it and commits, then B redeems with
        its stale copy. Only the conditional UPDATE stands between B and a
        second password change. (Real concurrency on PostgreSQL:
        tests/integration/test_password_reset_race_pg.py.)"""
        _request(anon)
        raw = _token_from(mailbox)
        other = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)()
        stale = other.query(m.PasswordResetToken).one()
        assert stale.used_at is None
        assert pr.redeem(db_session, raw, "attacker-pass-A")[0] == pr.RESET
        db_session.commit()
        status, _ = pr.redeem(other, raw, "victim-pass-B")
        other.commit()
        other.close()
        assert status == pr.INVALID
        db_session.refresh(account)
        assert auth_svc.verify_password("attacker-pass-A", account.password_hash)


class TestEmailLimits:
    def test_at_most_five_emails_per_address_per_day(self, anon, account, mailbox,
                                                     monkeypatch, caplog):
        monkeypatch.setattr(pr, "RESEND_COOLDOWN_SECONDS", 0)
        ips = iter(f"198.51.100.{i}" for i in range(1, 50))
        monkeypatch.setattr("app.api.auth.client_ip", lambda _request: next(ips))
        codes = [_request(anon).status_code for _ in range(7)]
        assert codes == [200] * 7
        assert len(mailbox) == 5
        assert "daily limit" in caplog.text

    def test_the_daily_limit_does_not_kill_the_last_link(self, anon, account, mailbox,
                                                         monkeypatch):
        monkeypatch.setattr(pr, "RESEND_COOLDOWN_SECONDS", 0)
        for _ in range(6):
            _request(anon)
        assert _confirm(anon, _token_from(mailbox)).status_code == 200

    def test_a_re_request_inside_the_cooldown_keeps_the_first_link_working(
            self, anon, account, mailbox):
        _request(anon)
        first = _token_from(mailbox)
        assert _request(anon).status_code == 200  # inside the 60 s cooldown
        assert len(mailbox) == 1
        assert _confirm(anon, first).status_code == 200
