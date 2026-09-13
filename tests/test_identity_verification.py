"""Section B — identity & location verification at onboarding.

Pins: the three questions and their validation, the IP cross-check (a
mismatch flags for review and NEVER blocks), the audit rows, the admin review
queue, the signup flag that scopes all of it to new accounts, and the
geolocation adapters' parsing.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.db import models as m
from app.integrations import geolocation
from app.services import identity
from tests.conftest import auth_headers


@pytest.fixture()
def new_user(db_session, test_user):
    """The canonical user, marked as a post-0039 signup."""
    test_user.identity_required = True
    db_session.commit()
    return test_user


@pytest.fixture()
def detected(monkeypatch):
    """Make IP geolocation answer whatever the test sets."""
    box = {"country": None}
    monkeypatch.setattr(geolocation, "lookup_country", lambda ip: box["country"])
    return box


def _events(db_session, event=None):
    query = select(m.AccountSecurityEvent)
    if event:
        query = query.where(m.AccountSecurityEvent.event == event)
    return db_session.execute(query).scalars().all()


class TestCountries:
    def test_the_list_is_public_and_complete(self, anon_client):
        body = anon_client.get("/onboarding/countries").json()
        codes = {c["code"] for c in body["countries"]}
        for code in ("US", "CA", "GB", "AU", "NZ", "IE", "SG", "PK"):
            assert code in codes
        assert len(codes) > 240

    def test_normalisation(self):
        from app.services.countries import normalize_country

        assert normalize_country(" us ") == "US"
        assert normalize_country("XX") is None
        assert normalize_country(None) is None


class TestSubmitIdentity:
    def test_individual_with_matching_location(self, client, db_session, new_user, detected):
        detected["country"] = "US"
        resp = client.put("/onboarding/identity",
                          json={"personal_country": "us", "account_type": "individual"})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["identity_complete"] is True
        assert body["next_step"] == "phone"
        assert body["under_review"] is False
        db_session.refresh(new_user)
        assert new_user.personal_country == "US"
        assert new_user.geo_check_status == "match"
        assert new_user.geo_review_status is None
        assert [e.event for e in _events(db_session)] == ["identity_submitted"]

    def test_company_country_may_differ_from_personal(self, client, db_session, new_user,
                                                      detected):
        detected["country"] = "PK"
        resp = client.put("/onboarding/identity", json={
            "personal_country": "PK", "account_type": "company",
            "company_name": "Acme Holdings LLC", "company_country": "US"})
        assert resp.status_code == 200, resp.text
        db_session.refresh(new_user)
        assert (new_user.personal_country, new_user.company_country) == ("PK", "US")
        assert new_user.company_name == "Acme Holdings LLC"
        assert new_user.geo_check_status == "match"

    def test_company_requires_a_company_country(self, client, new_user, detected):
        resp = client.put("/onboarding/identity",
                          json={"personal_country": "US", "account_type": "company"})
        assert resp.status_code == 422
        assert "company" in resp.json()["detail"].lower()

    @pytest.mark.parametrize("payload", [
        {"personal_country": "ZZ", "account_type": "individual"},
        {"personal_country": "US", "account_type": "partnership"},
        {"personal_country": "USA", "account_type": "individual"},
    ])
    def test_invalid_answers_are_refused(self, client, new_user, detected, payload):
        assert client.put("/onboarding/identity", json=payload).status_code == 422

    def test_a_mismatch_flags_for_review_and_does_not_block(self, client, db_session,
                                                           new_user, detected):
        detected["country"] = "NL"
        resp = client.put("/onboarding/identity",
                          json={"personal_country": "US", "account_type": "individual"})
        assert resp.status_code == 200, "a mismatch is a signal, not a rejection"
        assert resp.json()["under_review"] is True
        # The detected country is NOT echoed to the user (VPN-tuning oracle).
        assert "NL" not in resp.text
        db_session.refresh(new_user)
        assert new_user.geo_check_status == "mismatch"
        assert new_user.geo_detected_country == "NL"
        assert new_user.geo_review_status == "pending"
        (event,) = _events(db_session, "geo_mismatch")
        assert event.details_json["declared_country"] == "US"
        assert event.details_json["detected_country"] == "NL"

    def test_unknown_location_is_recorded_but_not_queued(self, client, db_session,
                                                         new_user, detected):
        detected["country"] = None
        client.put("/onboarding/identity",
                   json={"personal_country": "US", "account_type": "individual"})
        db_session.refresh(new_user)
        assert new_user.geo_check_status == "unknown"
        assert new_user.geo_review_status is None

    def test_resubmitting_does_not_clear_a_pending_review(self, client, db_session,
                                                          new_user, detected):
        detected["country"] = "NL"
        client.put("/onboarding/identity",
                   json={"personal_country": "US", "account_type": "individual"})
        detected["country"] = "US"
        client.put("/onboarding/identity",
                   json={"personal_country": "US", "account_type": "individual"})
        db_session.refresh(new_user)
        assert new_user.geo_review_status == "pending", "only an admin clears a review"

    def test_status_endpoint(self, client, new_user):
        body = client.get("/onboarding/verification").json()
        assert body["identity_required"] is True
        assert body["next_step"] == "identity"
        assert body["phone_verified"] is False


class TestSignupScopesTheFlow:
    def test_new_signups_are_marked_identity_required(self, anon_client, db_session):
        resp = anon_client.post("/auth/signup",
                                json={"email": "fresh@example.com", "password": "Sup3rSecret!"})
        assert resp.status_code == 201, resp.text
        user_out = resp.json()["user"]
        assert user_out["identity_required"] is True
        assert user_out["identity_complete"] is False
        assert user_out["phone_verified"] is False
        row = db_session.execute(select(m.User).where(
            m.User.email == "fresh@example.com")).scalar_one()
        assert row.identity_required is True
        assert row.signup_ip == "testclient"

    def test_established_accounts_are_not(self, client, test_user):
        body = client.get("/auth/me").json()
        assert body["identity_required"] is False


class TestPhoneGate:
    def test_outreach_launch_needs_a_verified_phone(self, client, db_session, new_user,
                                                    email_sequence, verified_leads):
        resp = client.post(f"/sequences/{email_sequence.id}/enroll", json={})
        assert resp.status_code == 403
        assert resp.json()["detail"] == identity.PHONE_NOT_VERIFIED

    def test_a_verified_phone_opens_the_gate(self, client, db_session, new_user,
                                             email_sequence, verified_leads, gmail_account):
        new_user.phone_verified = True
        db_session.commit()
        resp = client.post(f"/sequences/{email_sequence.id}/enroll", json={})
        assert resp.status_code != 403, resp.text

    def test_the_kill_switch_disables_the_gate(self, monkeypatch, new_user):
        from app.config import settings

        monkeypatch.setattr(settings, "require_phone_verification", False)
        identity.require_verified_phone(new_user)  # does not raise

    def test_pre_0039_accounts_are_never_gated(self, test_user):
        assert test_user.identity_required is False
        identity.require_verified_phone(test_user)  # does not raise


class TestAdminReview:
    @pytest.fixture()
    def admin(self, db_session):
        user = m.User(email="admin@leadpilot.dev", is_admin=True, email_verified=True)
        db_session.add(user)
        db_session.commit()
        return user

    @pytest.fixture()
    def flagged(self, client, new_user, detected):
        detected["country"] = "RU"
        client.put("/onboarding/identity",
                   json={"personal_country": "GB", "account_type": "individual"})
        return new_user

    def test_pending_reviews_are_listed(self, client, admin, flagged):
        body = client.get("/admin/identity-reviews", headers=auth_headers(admin)).json()
        assert body["pending_count"] == 1
        (review,) = body["reviews"]
        assert review["email"] == flagged.email
        assert (review["personal_country"], review["geo_detected_country"]) == ("GB", "RU")

    def test_non_admins_cannot_see_the_queue(self, client, flagged):
        assert client.get("/admin/identity-reviews").status_code == 403

    def test_a_decision_is_recorded_and_audited(self, client, db_session, admin, flagged):
        resp = client.post(f"/admin/identity-reviews/{flagged.id}",
                           json={"decision": "cleared", "note": "Travelling, confirmed"},
                           headers=auth_headers(admin))
        assert resp.status_code == 200, resp.text
        db_session.refresh(flagged)
        assert flagged.geo_review_status == "cleared"
        assert flagged.geo_reviewed_by == admin.email
        assert _events(db_session, "geo_review_cleared")
        assert client.get("/admin/identity-reviews",
                          headers=auth_headers(admin)).json()["pending_count"] == 0

    def test_an_unknown_decision_is_refused(self, client, admin, flagged):
        resp = client.post(f"/admin/identity-reviews/{flagged.id}",
                           json={"decision": "ban"}, headers=auth_headers(admin))
        assert resp.status_code == 422

    def test_security_events_are_readable_by_admins(self, client, admin, flagged):
        rows = client.get(f"/admin/security-events?user_id={flagged.id}",
                          headers=auth_headers(admin)).json()
        assert any(r["event"] == "geo_mismatch" for r in rows)


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


class TestGeolocationAdapters:
    @pytest.mark.parametrize("ip,public", [
        ("8.8.8.8", True), ("127.0.0.1", False), ("10.1.2.3", False),
        ("192.168.0.9", False), ("testclient", False), ("", False),
        ("2001:4860:4860::8888", True), ("::1", False),
    ])
    def test_public_ip_detection(self, ip, public):
        assert geolocation.is_public_ip(ip) is public

    def test_ipapi_co_parsing(self, monkeypatch):
        fake = _FakeHttp(httpx.Response(200, json={"ip": "8.8.8.8", "country_code": "US"}))
        monkeypatch.setattr(geolocation, "_http", lambda: fake)
        assert geolocation.IpapiCoProvider().lookup("8.8.8.8").country_code == "US"
        assert "8.8.8.8" in fake.calls[0][0]

    def test_ipinfo_parsing_and_token(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "geolocation_api_key", "tok")
        fake = _FakeHttp(httpx.Response(200, json={"ip": "1.1.1.1", "country": "au"}))
        monkeypatch.setattr(geolocation, "_http", lambda: fake)
        assert geolocation.IpinfoProvider().lookup("1.1.1.1").country_code == "AU"
        assert fake.calls[0][1] == {"token": "tok"}

    def test_lookup_never_raises(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "geolocation_provider", "ipapi_co")
        fake = _FakeHttp(httpx.Response(429, json={"error": True, "reason": "RateLimited"}))
        monkeypatch.setattr(geolocation, "_http", lambda: fake)
        assert geolocation.lookup_country("8.8.8.8") is None

    def test_private_addresses_are_never_sent_to_a_provider(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "geolocation_provider", "ipapi_co")
        monkeypatch.setattr(geolocation, "_http",
                            lambda: pytest.fail("a private IP reached the provider"))
        assert geolocation.lookup_country("192.168.1.1") is None
