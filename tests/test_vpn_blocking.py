"""Section D — VPN / proxy / Tor / datacenter blocking at signup and login.

Real requests through the real auth handlers from a controllable source IP
(the _WithClientIP shim from test_rate_limit_auth), with the detection
provider replaced by a scripted fake. Pins: blocking, the user-facing message,
the audit row, the feature flag, allowlist, private-IP skip, fail-open vs
fail-closed, caching, and the two providers' parsing.
"""

from __future__ import annotations

import inspect

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import settings
from app.db import models as m
from app.db.base import get_db
from app.integrations import ip_intelligence
from app.main import app
from app.services import auth as auth_svc
from app.services import network_guard
from tests.test_rate_limit_auth import _WithClientIP, _route_for

PASSWORD = "CorrectHorse!1"
VPN_IP, HOME_IP = "185.220.101.1", "73.15.20.9"


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.flagged: dict[str, dict] = {}
        self.calls: list[str] = []
        self.error: Exception | None = None

    def assess(self, ip):
        self.calls.append(ip)
        if self.error:
            raise self.error
        return ip_intelligence.IpRisk(ip=ip, provider=self.name, **self.flagged.get(ip, {}))


@pytest.fixture()
def provider(monkeypatch):
    fake = FakeProvider()
    fake.flagged[VPN_IP] = {"is_vpn": True}
    monkeypatch.setattr(ip_intelligence, "get_provider", lambda name=None: fake)
    monkeypatch.setattr(settings, "vpn_block_enabled", True)
    return fake


@pytest.fixture()
def client_from(db_session):
    def _make(ip: str) -> TestClient:
        app.dependency_overrides[get_db] = lambda: db_session
        return TestClient(_WithClientIP(app), headers={"X-Test-Client-IP": ip})

    yield _make
    app.dependency_overrides.clear()


@pytest.fixture()
def account(db_session):
    user = m.User(email="member@example.com", email_verified=True,
                  password_hash=auth_svc.hash_password(PASSWORD))
    db_session.add(user)
    db_session.commit()
    return user


def _signup(client, email="new@example.com"):
    return client.post("/auth/signup", json={"email": email, "password": PASSWORD})


def _login(client, email="member@example.com"):
    return client.post("/auth/login", json={"email": email, "password": PASSWORD})


@pytest.mark.parametrize("path", ["/auth/login", "/auth/signup"])
def test_both_auth_routes_run_the_network_guard(path):
    source = inspect.getsource(_route_for(path, "POST").endpoint)
    assert "network_guard.enforce_clean_network(" in source
    # After the limiter, so blocked floods still spend quota.
    assert source.index("enforce_rate_limit(") < source.index("enforce_clean_network(")


class TestBlocking:
    def test_signup_through_a_vpn_is_refused(self, provider, client_from, db_session):
        resp = _signup(client_from(VPN_IP))
        assert resp.status_code == 403
        assert "disable your VPN" in resp.json()["detail"]
        assert resp.headers[network_guard.BLOCK_HEADER] == network_guard.VPN_BLOCKED
        assert db_session.execute(select(m.User)).first() is None, "no account was created"
        (event,) = db_session.execute(select(m.AccountSecurityEvent)).scalars()
        assert event.event == "signup_blocked_vpn"
        assert event.ip == VPN_IP and event.email == "new@example.com"
        assert event.details_json["reasons"] == ["vpn"]

    def test_login_through_a_vpn_is_refused_before_the_password_check(
            self, provider, client_from, account, monkeypatch):
        monkeypatch.setattr(auth_svc, "verify_password",
                            lambda *a: pytest.fail("password checked for a blocked login"))
        resp = _login(client_from(VPN_IP))
        assert resp.status_code == 403
        assert "normal network" in resp.json()["detail"]

    @pytest.mark.parametrize("flags", [{"is_proxy": True}, {"is_tor": True},
                                       {"is_datacenter": True}])
    def test_proxy_tor_and_datacenter_are_blocked_too(self, provider, client_from, account,
                                                      flags):
        provider.flagged["45.9.9.9"] = flags
        assert _login(client_from("45.9.9.9")).status_code == 403

    def test_a_clean_network_is_unaffected(self, provider, client_from, account):
        assert _login(client_from(HOME_IP)).status_code == 200
        assert _signup(client_from(HOME_IP)).status_code == 201


class TestWhenTheGuardStandsDown:
    def test_flag_off_means_no_lookup(self, provider, client_from, account, monkeypatch):
        monkeypatch.setattr(settings, "vpn_block_enabled", False)
        assert _login(client_from(VPN_IP)).status_code == 200
        assert provider.calls == []

    def test_unset_flag_is_on_only_in_production(self, monkeypatch):
        monkeypatch.setattr(settings, "vpn_block_enabled", None)
        monkeypatch.setattr(settings, "app_env", "production")
        assert settings.vpn_blocking_active is True
        monkeypatch.setattr(settings, "app_env", "development")
        assert settings.vpn_blocking_active is False

    def test_private_and_test_addresses_are_not_looked_up(self, provider, client_from,
                                                          account):
        assert _login(client_from("10.0.0.5")).status_code == 200
        assert provider.calls == []

    def test_allowlisted_ip(self, provider, client_from, account, monkeypatch):
        monkeypatch.setattr(settings, "vpn_allowlist_ips", f"1.2.3.4, {VPN_IP}")
        assert _login(client_from(VPN_IP)).status_code == 200

    def test_provider_outage_fails_open_by_default(self, provider, client_from, account):
        provider.error = ip_intelligence.IpIntelligenceError("quota exceeded")
        assert _login(client_from(VPN_IP)).status_code == 200

    def test_provider_outage_can_fail_closed(self, provider, client_from, account,
                                             monkeypatch):
        monkeypatch.setattr(settings, "vpn_detection_fail_closed", True)
        provider.error = ip_intelligence.IpIntelligenceError("quota exceeded")
        resp = _login(client_from(VPN_IP))
        assert resp.status_code == 503
        assert "try again" in resp.json()["detail"]


class TestCaching:
    def test_a_verdict_is_cached_per_ip(self, monkeypatch):
        fake = FakeProvider()
        monkeypatch.setattr(ip_intelligence, "get_provider", lambda name=None: fake)
        ip_intelligence.assess(HOME_IP)
        ip_intelligence.assess(HOME_IP)
        assert fake.calls == [HOME_IP]

    def test_errors_are_not_cached(self, monkeypatch):
        fake = FakeProvider()
        fake.error = ip_intelligence.IpIntelligenceError("down")
        monkeypatch.setattr(ip_intelligence, "get_provider", lambda name=None: fake)
        for _ in range(2):
            with pytest.raises(ip_intelligence.IpIntelligenceError):
                ip_intelligence.assess(HOME_IP)
        assert len(fake.calls) == 2

    def test_transport_errors_become_intelligence_errors(self, monkeypatch):
        class _Broken:
            name = "broken"

            def assess(self, ip):
                raise httpx.ConnectError("no route")

        monkeypatch.setattr(ip_intelligence, "get_provider", lambda name=None: _Broken())
        with pytest.raises(ip_intelligence.IpIntelligenceError):
            ip_intelligence.assess("9.9.9.9")


class _FakeHttp:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, url, params=None, headers=None):
        self.calls.append((url, params))
        return self.response


class TestProviders:
    @pytest.mark.parametrize("entry,reasons", [
        ({"proxy": "yes", "type": "VPN"}, ["vpn"]),
        ({"proxy": "yes", "type": "TOR"}, ["tor"]),
        ({"proxy": "yes", "type": "SOCKS5"}, ["proxy"]),
        ({"proxy": "no", "type": "Hosting"}, ["datacenter"]),
        ({"proxy": "no", "type": "Residential"}, []),
    ])
    def test_proxycheck_parsing(self, monkeypatch, entry, reasons):
        fake = _FakeHttp(httpx.Response(200, json={"status": "ok", "8.8.8.8": entry}))
        monkeypatch.setattr(ip_intelligence, "_http", lambda: fake)
        assert ip_intelligence.ProxycheckProvider().assess("8.8.8.8").reasons == reasons
        assert fake.calls[0][1]["vpn"] == 1

    def test_proxycheck_denied_is_an_error(self, monkeypatch):
        fake = _FakeHttp(httpx.Response(200, json={"status": "denied", "message": "quota"}))
        monkeypatch.setattr(ip_intelligence, "_http", lambda: fake)
        with pytest.raises(ip_intelligence.IpIntelligenceError):
            ip_intelligence.ProxycheckProvider().assess("8.8.8.8")

    def test_ipqualityscore_parsing(self, monkeypatch):
        monkeypatch.setattr(settings, "vpn_detection_api_key", "k")
        fake = _FakeHttp(httpx.Response(200, json={
            "success": True, "vpn": False, "active_vpn": False, "tor": False,
            "proxy": False, "connection_type": "Data Center"}))
        monkeypatch.setattr(ip_intelligence, "_http", lambda: fake)
        assert ip_intelligence.IpqsProvider().assess("8.8.8.8").reasons == ["datacenter"]

    def test_ipqualityscore_needs_a_key(self, monkeypatch):
        monkeypatch.setattr(settings, "vpn_detection_api_key", "")
        with pytest.raises(ip_intelligence.IpIntelligenceError):
            ip_intelligence.IpqsProvider().assess("8.8.8.8")

    def test_unknown_provider_name(self, monkeypatch):
        monkeypatch.setattr(settings, "vpn_detection_provider", "crystal-ball")
        with pytest.raises(ip_intelligence.IpIntelligenceError):
            ip_intelligence.get_provider()
