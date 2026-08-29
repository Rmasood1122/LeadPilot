"""Feature 1 — signup email verification.

Every claim made in docs/features/email-verification.md has a test here. The
ones that matter most are the negative paths: an expiry that never fires, a
token that can be replayed, or a gate that lets an unverified account through
all look identical to a working feature until a real user hits them.

The email is read from the in-process `mailbox` fixture (EMAIL_PROVIDER=memory,
set in conftest), so these tests assert on the message a human would actually
receive — link included — not on internal state that happens to be adjacent.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select

from app.db import models as m
from app.services import email_verification as ev
from app.services.email_sender import EmailSendError
from tests.conftest import complete_verification, verification_link

EMAIL = "newuser@x.com"
PASSWORD = "hunter22!"


def _signup(client, email=EMAIL, password=PASSWORD):
    r = client.post("/auth/signup", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()


def _headers(tokens):
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _verify_path(link: str) -> str:
    parts = urlparse(link)
    return f"{parts.path}?{parts.query}"


# --------------------------------------------------------------------------
# Signup
# --------------------------------------------------------------------------


class TestSignupSendsVerification:
    def test_new_account_is_unverified_and_gets_an_email(self, client,
                                                         db_session, mailbox):
        body = _signup(client)

        user = db_session.execute(
            select(m.User).where(m.User.email == EMAIL)
        ).scalars().one()
        assert user.email_verified is False
        assert user.email_verified_at is None

        assert body["email_verification_required"] is True
        assert body["verification_email_sent"] is True
        assert body["user"]["email_verified"] is False

        assert len(mailbox) == 1
        assert mailbox[0]["to"] == EMAIL
        assert "Verify your" in mailbox[0]["subject"]

    def test_email_contains_a_working_absolute_link(self, client, mailbox):
        _signup(client)
        link = verification_link(mailbox)
        # Absolute and pointed at the API, because a static-export frontend has
        # no server to receive it.
        assert link.startswith("http://testserver/auth/verify?token=")
        token = parse_qs(urlparse(link).query)["token"][0]
        assert len(token) >= 32

    def test_the_raw_token_is_never_stored(self, client, db_session, mailbox):
        _signup(client)
        raw = parse_qs(urlparse(verification_link(mailbox)).query)["token"][0]

        row = db_session.execute(
            select(m.EmailVerificationToken)
        ).scalars().one()
        assert row.token_hash != raw
        assert row.token_hash == ev.token_hash(raw)
        assert len(row.token_hash) == 64

    def test_token_expires_24_hours_out(self, client, db_session, mailbox):
        _signup(client)
        row = db_session.execute(
            select(m.EmailVerificationToken)
        ).scalars().one()
        expires = ev._as_aware(row.expires_at)
        delta = expires - datetime.now(timezone.utc)
        # Bounded either side rather than compared exactly: the value is
        # computed from wall-clock time inside the request.
        assert timedelta(hours=23, minutes=55) < delta <= timedelta(hours=24)

    def test_signup_still_succeeds_when_the_mail_transport_is_down(
        self, client, db_session, monkeypatch
    ):
        """A dead relay must not destroy the account the user just created.

        The address would then be taken, the password lost, and the signup
        unrepeatable — a far worse outcome than an account that needs a resend.
        """
        import app.api.auth as auth_api

        def boom(*_a, **_kw):
            raise EmailSendError("relay refused connection")

        monkeypatch.setattr(auth_api.verify_svc, "send_link", boom)

        r = client.post("/auth/signup",
                        json={"email": "down@x.com", "password": PASSWORD})
        assert r.status_code == 201
        assert r.json()["verification_email_sent"] is False
        assert db_session.execute(
            select(m.User).where(m.User.email == "down@x.com")
        ).scalars().one() is not None


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


class TestUnverifiedIsBlocked:
    def test_authenticated_route_returns_403_email_not_verified(self, client):
        tokens = _signup(client)
        r = client.get("/auth/me", headers=_headers(tokens))
        assert r.status_code == 403
        assert r.json()["detail"] == "EMAIL_NOT_VERIFIED"

    def test_the_gate_is_not_limited_to_auth_me(self, client):
        """It is one dependency, so it covers routes nobody remembered to guard."""
        tokens = _signup(client)
        for path in ("/auth/me", "/me/theme", "/onboarding/state"):
            r = client.get(path, headers=_headers(tokens))
            assert r.status_code == 403, f"{path} was not gated"
            assert r.json()["detail"] == "EMAIL_NOT_VERIFIED"

    def test_it_is_403_not_401_so_the_client_does_not_log_the_user_out(
        self, client
    ):
        """401 would send the frontend into refresh-then-retry and end in a
        logout for someone whose only problem is an unread email."""
        tokens = _signup(client)
        assert client.get("/auth/me",
                          headers=_headers(tokens)).status_code != 401

    def test_login_still_works_while_unverified(self, client):
        """Otherwise there is no session from which to press "resend"."""
        _signup(client)
        r = client.post("/auth/login",
                        json={"email": EMAIL, "password": PASSWORD})
        assert r.status_code == 200
        assert r.json()["user"]["email_verified"] is False

    def test_kill_switch_disables_the_gate(self, client, monkeypatch):
        from app.config import settings

        tokens = _signup(client)
        assert client.get("/auth/me",
                          headers=_headers(tokens)).status_code == 403
        monkeypatch.setattr(settings, "require_email_verification", False)
        assert client.get("/auth/me",
                          headers=_headers(tokens)).status_code == 200

    def test_users_created_before_the_feature_are_not_blocked(self, client,
                                                              db_session):
        """Mirrors migration 0015's backfill: pre-existing accounts stay in."""
        legacy = db_session.execute(
            select(m.User).where(m.User.email == "test@leadpilot.dev")
        ).scalars().one()
        assert legacy.email_verified is True
        assert client.get("/auth/me").status_code == 200


# --------------------------------------------------------------------------
# Clicking the link
# --------------------------------------------------------------------------


class TestVerifyEndpoint:
    def test_click_verifies_and_redirects_to_the_frontend(self, client,
                                                          db_session, mailbox):
        tokens = _signup(client)
        link = verification_link(mailbox)

        resp = client.get(_verify_path(link), follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "http://frontend.test/login?verified=true"

        db_session.expire_all()
        user = db_session.execute(
            select(m.User).where(m.User.email == EMAIL)
        ).scalars().one()
        assert user.email_verified is True
        assert user.email_verified_at is not None

        assert client.get("/auth/me", headers=_headers(tokens)).status_code == 200

    def test_a_used_link_cannot_be_replayed(self, client, mailbox):
        _signup(client)
        path = _verify_path(verification_link(mailbox))

        assert client.get(path, follow_redirects=False).status_code == 302
        second = client.get(path, follow_redirects=False)
        assert second.status_code == 302
        # Already verified — distinct from expired, so the page can say so.
        assert second.headers["location"].endswith("?verified=already")

    def test_expired_link_is_refused(self, client, db_session, mailbox):
        """Forces the clock rather than waiting 24 hours."""
        _signup(client)
        path = _verify_path(verification_link(mailbox))

        row = db_session.execute(
            select(m.EmailVerificationToken)
        ).scalars().one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db_session.commit()

        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("?error=expired")

        db_session.expire_all()
        user = db_session.execute(
            select(m.User).where(m.User.email == EMAIL)
        ).scalars().one()
        assert user.email_verified is False

    def test_a_link_that_expires_exactly_now_is_refused(self, client,
                                                        db_session, mailbox):
        """Boundary: <= now, not < now. An off-by-one here silently grants an
        extra request's worth of life to every expired link."""
        _signup(client)
        path = _verify_path(verification_link(mailbox))
        row = db_session.execute(
            select(m.EmailVerificationToken)
        ).scalars().one()
        row.expires_at = datetime.now(timezone.utc)
        db_session.commit()
        resp = client.get(path, follow_redirects=False)
        assert resp.headers["location"].endswith("?error=expired")

    @pytest.mark.parametrize("token", ["", "not-a-real-token", "x" * 200])
    def test_unknown_tokens_redirect_to_invalid(self, client, token):
        resp = client.get(f"/auth/verify?token={token}", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("?error=invalid")

    def test_verify_requires_no_authentication(self, anon_client, client,
                                               mailbox):
        """The link is clicked from an inbox, often in a browser with no session."""
        _signup(client)
        path = _verify_path(verification_link(mailbox))
        assert anon_client.get(path, follow_redirects=False).status_code == 302


# --------------------------------------------------------------------------
# Resend
# --------------------------------------------------------------------------


class TestResend:
    def test_resend_sends_a_second_email_with_a_different_link(self, client,
                                                              mailbox):
        _signup(client)
        first = verification_link(mailbox)

        r = client.post("/auth/resend-verification", json={"email": EMAIL})
        assert r.status_code == 202
        assert len(mailbox) == 2
        second = verification_link(mailbox)
        assert second != first

    def test_resending_invalidates_the_previous_link(self, client, mailbox):
        """Five resends must not leave five live links for 24 hours each."""
        _signup(client)
        old_path = _verify_path(verification_link(mailbox))
        client.post("/auth/resend-verification", json={"email": EMAIL})
        new_path = _verify_path(verification_link(mailbox))

        stale = client.get(old_path, follow_redirects=False)
        assert stale.headers["location"].endswith("?error=expired")

        fresh = client.get(new_path, follow_redirects=False)
        assert fresh.headers["location"].endswith("?verified=true")

    def test_the_new_link_works_end_to_end(self, client, mailbox):
        tokens = _signup(client)
        client.post("/auth/resend-verification", json={"email": EMAIL})
        assert complete_verification(client, mailbox) == 302
        assert client.get("/auth/me", headers=_headers(tokens)).status_code == 200

    def test_unknown_address_is_indistinguishable_from_a_known_one(self,
                                                                   client,
                                                                   mailbox):
        """No account-existence oracle — /auth/login went to the same trouble."""
        _signup(client)
        mailbox.clear()

        known = client.post("/auth/resend-verification", json={"email": EMAIL})
        unknown = client.post("/auth/resend-verification",
                              json={"email": "nobody@nowhere.com"})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        # ...and nothing was sent to the address that has no account.
        assert [msg["to"] for msg in mailbox] == [EMAIL]

    def test_already_verified_account_gets_no_further_email(self, client,
                                                            mailbox):
        _signup(client)
        complete_verification(client, mailbox)
        mailbox.clear()

        r = client.post("/auth/resend-verification", json={"email": EMAIL})
        assert r.status_code == 202
        assert mailbox == []

    def test_resend_is_rate_limited(self, client, monkeypatch):
        """Otherwise it is a free mail-bomb aimed at any address you name.

        The limit lives on app.core.config.settings as RATE_LIMIT_AUTH — the
        SECOND settings object in this codebase, and the one enforce_rate_limit
        actually reads. Patching app.config.settings here would set a field
        nothing consults and produce a test that passes while the endpoint is
        wide open.
        """
        from app.core.config import settings as core_settings

        limit = 3
        monkeypatch.setattr(core_settings, "RATE_LIMIT_AUTH", limit)
        _signup(client)  # burns one slot on both keys

        codes = [
            client.post("/auth/resend-verification",
                        json={"email": EMAIL}).status_code
            for _ in range(limit + 2)
        ]
        assert 429 in codes, f"never rate limited: {codes}"
        # ...and once it engages it stays engaged for the window.
        assert codes[-1] == 429, codes


# --------------------------------------------------------------------------
# Transport selection
# --------------------------------------------------------------------------


class TestEmailSender:
    def test_unknown_provider_raises_instead_of_silently_logging(self,
                                                                monkeypatch):
        """A typo'd EMAIL_PROVIDER in production must not degrade to writing
        every verification link into a log file nobody reads."""
        from app.config import settings
        from app.services.email_sender import send_email

        monkeypatch.setattr(settings, "email_provider", "resnd")
        with pytest.raises(EmailSendError, match="not a known transport"):
            send_email(to="a@b.com", subject="s", html="<p>h</p>", text="t")

    def test_resend_without_a_key_names_the_missing_variable(self, monkeypatch):
        from app.config import settings
        from app.services.email_sender import send_email

        monkeypatch.setattr(settings, "email_provider", "resend")
        monkeypatch.setattr(settings, "resend_api_key", "")
        with pytest.raises(EmailSendError, match="RESEND_API_KEY"):
            send_email(to="a@b.com", subject="s", html="<p>h</p>", text="t")

    def test_smtp_without_a_host_names_the_missing_variable(self, monkeypatch):
        from app.config import settings
        from app.services.email_sender import send_email

        monkeypatch.setattr(settings, "email_provider", "smtp")
        monkeypatch.setattr(settings, "smtp_host", "")
        with pytest.raises(EmailSendError, match="SMTP_HOST"):
            send_email(to="a@b.com", subject="s", html="<p>h</p>", text="t")
