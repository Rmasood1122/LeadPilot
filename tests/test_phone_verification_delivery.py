"""Product defect #5: REQUIRE_PHONE_VERIFICATION=true (the default) with
SMS_PROVIDER=console (also the default, and what production runs today: no
SMS_* or TWILIO_* in render.yaml). The console transport delivers nothing, so
no new account could ever pass the phone gate -- they could not launch
outreach, buy a plan or mint a share link.

Chosen fix (see docs/program/fixes/product-defects.md #5): the phone gate is
enforced only when a code can actually be delivered. A deployment that
requires verification but cannot deliver it does not gate, and says so loudly:
a startup log warning and an admin-visible warning (GET /admin/config-warnings,
shown as a banner in the admin panel). A correctly configured deployment
(SMS_PROVIDER=twilio with all three TWILIO_* values) gates exactly as before.
Failing the boot instead was rejected: production runs this configuration
today, so the next deploy would take the API down, and the sealed
tests/test_production_guard.py defines a "fully configured production" with no
SMS settings that must keep starting.
"""

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services import identity


@pytest.fixture()
def new_user(db_session, test_user):
    test_user.identity_required = True
    db_session.commit()
    return test_user


def _configure(monkeypatch, *, provider, env="production", require=True, twilio=True):
    monkeypatch.setattr(settings, "app_env", env)
    monkeypatch.setattr(settings, "sms_provider", provider)
    monkeypatch.setattr(settings, "require_phone_verification", require)
    for key, value in (("twilio_account_sid", "AC123"), ("twilio_auth_token", "tok"),
                       ("twilio_from_number", "+15550001111")):
        monkeypatch.setattr(settings, key, value if twilio else "")


class TestGateFollowsDeliverability:
    def test_console_in_production_does_not_lock_new_accounts_out(self, monkeypatch, new_user):
        _configure(monkeypatch, provider="console")
        identity.require_verified_phone(new_user)  # does not raise
        status = identity.status(new_user)
        assert status["phone_required"] is False
        assert status["next_step"] != "phone"

    def test_a_correctly_configured_deployment_still_gates(self, monkeypatch, new_user):
        _configure(monkeypatch, provider="twilio")
        with pytest.raises(HTTPException) as exc:
            identity.require_verified_phone(new_user)
        assert exc.value.detail == identity.PHONE_NOT_VERIFIED
        assert identity.status(new_user)["phone_required"] is True

    # Review M6: no silent fail-open. A provider that is set but broken (a
    # typo, Twilio missing a key, the in-process transport in production)
    # keeps the gate ON and is reported loudly; only an explicit console or
    # empty provider in production turns the gate off.
    @pytest.mark.parametrize("provider,twilio", [
        ("twillio", True),     # typo
        ("twilio", False),     # incomplete Twilio
        ("memory", True),      # test transport in production
    ])
    def test_a_broken_provider_keeps_the_gate_on_and_warns(self, monkeypatch, new_user,
                                                          provider, twilio):
        _configure(monkeypatch, provider=provider, twilio=twilio)
        with pytest.raises(HTTPException):
            identity.require_verified_phone(new_user)
        assert identity.status(new_user)["phone_required"] is True
        (warning,) = identity.config_warnings()
        assert warning["key"] == "sms_provider_misconfigured"
        assert "SMS_PROVIDER" in warning["message"]

    def test_empty_provider_in_production_is_like_console(self, monkeypatch, new_user):
        _configure(monkeypatch, provider="")
        identity.require_verified_phone(new_user)  # does not raise
        assert [w["key"] for w in identity.config_warnings()] == [
            "phone_verification_undeliverable"]

    def test_console_outside_production_keeps_the_gate(self, monkeypatch, new_user):
        _configure(monkeypatch, provider="console", env="development")
        with pytest.raises(HTTPException):
            identity.require_verified_phone(new_user)

    def test_memory_transport_gates_in_tests(self, monkeypatch, new_user):
        _configure(monkeypatch, provider="memory", env="test")
        with pytest.raises(HTTPException):
            identity.require_verified_phone(new_user)

    def test_kill_switch_off_means_no_gate_and_no_warning(self, monkeypatch, new_user):
        _configure(monkeypatch, provider="console", require=False)
        identity.require_verified_phone(new_user)
        assert identity.config_warnings() == []


class TestWarningIsVisible:
    def test_warning_names_the_setting_and_the_fix(self, monkeypatch):
        _configure(monkeypatch, provider="console")
        (warning,) = identity.config_warnings()
        assert warning["key"] == "phone_verification_undeliverable"
        assert "SMS_PROVIDER" in warning["message"]
        assert "twilio" in warning["message"].lower()

    def test_no_warning_when_delivery_works(self, monkeypatch):
        _configure(monkeypatch, provider="twilio")
        assert identity.config_warnings() == []

    def test_admins_see_it_and_others_do_not(self, client, db_session, test_user, monkeypatch):
        _configure(monkeypatch, provider="console")
        assert client.get("/admin/config-warnings").status_code == 403
        test_user.is_admin = True
        db_session.commit()
        body = client.get("/admin/config-warnings").json()
        assert [w["key"] for w in body] == ["phone_verification_undeliverable"]

    def test_startup_logs_it(self, monkeypatch, caplog):
        _configure(monkeypatch, provider="console")
        with caplog.at_level("WARNING"):
            identity.log_config_warnings()
        assert "SMS_PROVIDER" in caplog.text

    def test_a_misconfigured_provider_is_a_startup_error(self, monkeypatch, caplog):
        _configure(monkeypatch, provider="twillio")
        with caplog.at_level("ERROR"):
            identity.log_config_warnings()
        assert any(r.levelname == "ERROR" and "SMS_PROVIDER" in r.getMessage()
                   for r in caplog.records)


def test_enroll_is_not_blocked_on_an_undeliverable_deployment(
        client, monkeypatch, new_user, email_sequence, verified_leads, gmail_account):
    _configure(monkeypatch, provider="console")
    resp = client.post(f"/sequences/{email_sequence.id}/enroll", json={})
    assert resp.status_code != 403, resp.text


def test_auth_me_reports_whether_the_phone_is_required(client, monkeypatch, new_user):
    _configure(monkeypatch, provider="console")
    assert client.get("/auth/me").json()["phone_required"] is False
    _configure(monkeypatch, provider="twilio")
    assert client.get("/auth/me").json()["phone_required"] is True
