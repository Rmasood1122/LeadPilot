"""Section C — phone verification by SMS one-time code.

Pins the whole loop through the real endpoints and the memory SMS transport
(the code a test types is the code the user would have received), plus every
limit: resend cooldown, per-account and per-number send limits, wrong-attempt
lockout, expiry, the one-number-one-account rule, and the Twilio adapter.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import select

from app.db import models as m
from app.integrations import sms
from app.services import phone_verification as phone_svc

PHONE = "+14155550123"


@pytest.fixture()
def new_user(db_session, test_user):
    test_user.identity_required = True
    db_session.commit()
    return test_user


@pytest.fixture()
def no_cooldown(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "phone_otp_resend_cooldown_seconds", 0)


def _code(outbox) -> str:
    assert outbox, "no SMS was sent"
    match = re.search(r"\b(\d{6})\b", outbox[-1]["body"])
    assert match, outbox[-1]["body"]
    return match.group(1)


class TestNormalisation:
    @pytest.mark.parametrize("raw,expected", [
        ("+1 (415) 555-0123", "+14155550123"),
        ("0092 300 1234567", "+923001234567"),
        ("+44.20.7946.0958", "+442079460958"),
    ])
    def test_accepted_formats(self, raw, expected):
        assert phone_svc.normalize_phone(raw) == expected

    @pytest.mark.parametrize("raw", ["4155550123", "+0123456789", "+1415", "phone", ""])
    def test_rejected_formats(self, raw):
        with pytest.raises(phone_svc.PhoneVerificationError):
            phone_svc.normalize_phone(raw)


class TestHappyPath:
    def test_send_then_verify(self, client, db_session, new_user, sms_outbox):
        resp = client.post("/onboarding/phone/send", json={"phone_number": "+1 415 555 0123"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["phone_number_masked"] == "+14******123"
        assert sms_outbox[-1]["to"] == PHONE

        resp = client.post("/onboarding/phone/verify", json={"code": _code(sms_outbox)})
        assert resp.status_code == 200, resp.text
        assert resp.json()["phone_verified"] is True
        db_session.refresh(new_user)
        assert (new_user.phone_verified, new_user.phone_number) == (True, PHONE)
        events = {e.event for e in db_session.execute(select(m.AccountSecurityEvent)).scalars()}
        assert {"phone_code_sent", "phone_verified"} <= events

    def test_only_a_hash_is_stored(self, client, db_session, new_user, sms_outbox):
        client.post("/onboarding/phone/send", json={"phone_number": PHONE})
        row = db_session.execute(select(m.PhoneVerificationCode)).scalar_one()
        assert _code(sms_outbox) not in row.code_hash
        assert len(row.code_hash) == 64

    def test_a_verified_account_cannot_send_again(self, client, db_session, new_user):
        new_user.phone_verified = True
        db_session.commit()
        assert client.post("/onboarding/phone/send",
                           json={"phone_number": PHONE}).status_code == 409


class TestLimits:
    def test_resend_cooldown(self, client, new_user, sms_outbox):
        assert client.post("/onboarding/phone/send", json={"phone_number": PHONE}).status_code == 200
        resp = client.post("/onboarding/phone/send", json={"phone_number": PHONE})
        assert resp.status_code == 429
        assert int(resp.headers["Retry-After"]) > 0
        assert len(sms_outbox) == 1

    def test_a_resend_kills_the_earlier_code(self, client, new_user, sms_outbox, no_cooldown):
        client.post("/onboarding/phone/send", json={"phone_number": PHONE})
        first = _code(sms_outbox)
        client.post("/onboarding/phone/send", json={"phone_number": PHONE})
        second = _code(sms_outbox)
        if first == second:  # one-in-a-million collision; nothing to assert
            pytest.skip("codes collided")
        assert client.post("/onboarding/phone/verify", json={"code": first}).status_code == 400
        assert client.post("/onboarding/phone/verify", json={"code": second}).status_code == 200

    def test_send_is_rate_limited_per_account(self, client, monkeypatch, new_user, no_cooldown):
        from app.core.config import settings as core

        monkeypatch.setattr(core, "RATE_LIMIT_OTP_SEND", 2)
        codes = [client.post("/onboarding/phone/send",
                             json={"phone_number": f"+1415555012{i}"}).status_code
                 for i in range(3)]
        assert codes == [200, 200, 429]

    def test_send_is_rate_limited_per_number(self, client, db_session, monkeypatch,
                                             new_user, no_cooldown):
        """SMS pumping spreads across accounts at one number."""
        from app.core.config import settings as core
        from tests.conftest import auth_headers

        monkeypatch.setattr(core, "RATE_LIMIT_OTP_SEND", 2)
        others = []
        for i in range(3):
            user = m.User(email=f"pump{i}@example.com", email_verified=True)
            db_session.add(user)
            others.append(user)
        db_session.commit()
        codes = [client.post("/onboarding/phone/send", json={"phone_number": PHONE},
                             headers=auth_headers(u)).status_code for u in others]
        assert codes == [200, 200, 429]

    def test_wrong_codes_lock_the_code(self, client, monkeypatch, new_user, sms_outbox):
        from app.config import settings

        monkeypatch.setattr(settings, "phone_otp_max_attempts", 3)
        client.post("/onboarding/phone/send", json={"phone_number": PHONE})
        right = _code(sms_outbox)
        wrong = "000000" if right != "000000" else "111111"
        first = client.post("/onboarding/phone/verify", json={"code": wrong})
        assert first.status_code == 400 and first.headers["X-Attempts-Remaining"] == "2"
        client.post("/onboarding/phone/verify", json={"code": wrong})
        third = client.post("/onboarding/phone/verify", json={"code": wrong})
        assert "Too many" in third.json()["detail"]
        # Even the right code is dead now.
        assert client.post("/onboarding/phone/verify", json={"code": right}).status_code == 400

    def test_verify_is_rate_limited(self, client, monkeypatch, new_user, sms_outbox):
        from app.core.config import settings as core

        monkeypatch.setattr(core, "RATE_LIMIT_OTP_VERIFY", 2)
        client.post("/onboarding/phone/send", json={"phone_number": PHONE})
        codes = [client.post("/onboarding/phone/verify", json={"code": "999999"}).status_code
                 for _ in range(3)]
        assert codes[-1] == 429

    def test_an_expired_code_is_refused(self, db_session, new_user, sms_outbox):
        now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        phone_svc.send_code(db_session, new_user, PHONE, now=now)
        outcome, _ = phone_svc.verify_code(db_session, new_user, _code(sms_outbox),
                                           now=now + timedelta(hours=1))
        assert outcome == phone_svc.EXPIRED
        assert new_user.phone_verified is False

    def test_verify_without_a_code(self, client, new_user):
        resp = client.post("/onboarding/phone/verify", json={"code": "123456"})
        assert resp.status_code == 400 and "first" in resp.json()["detail"]


class TestOneNumberOneAccount:
    def test_a_number_verified_elsewhere_is_refused(self, client, db_session, new_user,
                                                    sms_outbox):
        db_session.add(m.User(email="owner@example.com", phone_number=PHONE,
                              phone_verified=True, email_verified=True))
        db_session.commit()
        resp = client.post("/onboarding/phone/send", json={"phone_number": PHONE})
        assert resp.status_code == 409
        assert not sms_outbox, "no SMS may be spent on a number that cannot verify"


class TestTransport:
    def test_send_failure_is_a_502_and_kills_the_code(self, client, db_session, monkeypatch,
                                                     new_user):
        def _boom(to, body):
            raise sms.SmsSendError("carrier said no")

        monkeypatch.setattr(sms, "send_sms", _boom)
        resp = client.post("/onboarding/phone/send", json={"phone_number": PHONE})
        assert resp.status_code == 502
        row = db_session.execute(select(m.PhoneVerificationCode)).scalar_one()
        assert row.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)

    def test_unknown_provider_fails_loudly(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "sms_provider", "carrier-pigeon")
        with pytest.raises(sms.SmsSendError):
            sms.send_sms(PHONE, "hi")

    def test_twilio_adapter(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "sms_provider", "twilio")
        monkeypatch.setattr(settings, "twilio_account_sid", "AC123")
        monkeypatch.setattr(settings, "twilio_auth_token", "secret")
        monkeypatch.setattr(settings, "twilio_from_number", "+15005550006")
        seen = {}

        class _Client:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def post(self, url, data=None, auth=None):
                seen.update(url=url, data=data, auth=auth)
                return httpx.Response(201, json={"sid": "SM1"})

        monkeypatch.setattr(sms, "_http", lambda: _Client())
        assert sms.send_sms(PHONE, "code 123456") == "SM1"
        assert seen["url"].endswith("/Accounts/AC123/Messages.json")
        assert seen["data"] == {"To": PHONE, "Body": "code 123456", "From": "+15005550006"}
        assert seen["auth"] == ("AC123", "secret")

    def test_twilio_without_credentials_fails_loudly(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "sms_provider", "twilio")
        monkeypatch.setattr(settings, "twilio_account_sid", "")
        with pytest.raises(sms.SmsSendError):
            sms.send_sms(PHONE, "hi")

    def test_console_transport_never_logs_the_code(self, monkeypatch, caplog):
        from app.config import settings

        monkeypatch.setattr(settings, "sms_provider", "console")
        with caplog.at_level("WARNING"):
            sms.send_sms(PHONE, "Your code is 482913")
        assert "482913" not in caplog.text
        assert PHONE not in caplog.text
