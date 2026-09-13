"""Feature 7 — Google Meet / Zoom adapters and the calendar reconnect flow.

These are MOCKED (httpx.MockTransport). They pin the request shapes the
adapters send, as checked against current docs, and the reconnect behaviour.
They do NOT prove the live APIs accept those requests -- that is
tests/test_meeting_platforms_live.py (skipped without credentials) and
scripts/verify_meeting_platforms.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.db import models as m
from app.integrations import google_meet, zoom
from app.integrations.plumbing import BaseHttpAdapter
from app.services import credentials, crypto

UTC = timezone.utc
START = datetime(2026, 9, 22, 15, 0, tzinfo=UTC)
FULL_SCOPES = ("https://www.googleapis.com/auth/gmail.send "
               "https://www.googleapis.com/auth/gmail.readonly "
               "https://www.googleapis.com/auth/calendar.events")
OLD_SCOPES = ("https://www.googleapis.com/auth/gmail.send "
              "https://www.googleapis.com/auth/gmail.readonly")


def _account(db, user, scopes):
    row = m.GmailAccount(
        user_id=user.id, email_address="me@leadpilot.dev", scopes=scopes,
        token_ciphertext=crypto.encrypt_json({"access_token": "a", "refresh_token": "r"}),
        token_expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(row)
    db.commit()
    return row


def _client(base_url, handler):
    return httpx.Client(base_url=base_url, transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setattr("app.integrations.gmail.get_valid_access_token",
                        lambda session, account: "tok")


# --------------------------------------------------------------------------
# Scope detection and the reconnect flow
# --------------------------------------------------------------------------


class TestReconnect:
    def test_scope_states(self, db_session, test_user):
        assert google_meet.calendar_scope_state(None) == "not_connected"
        account = _account(db_session, test_user, OLD_SCOPES)
        assert google_meet.calendar_scope_state(account) == "missing"
        account.scopes = FULL_SCOPES
        assert google_meet.calendar_scope_state(account) == "granted"
        account.scopes = "https://www.googleapis.com/auth/calendar"
        assert google_meet.calendar_scope_state(account) == "granted"
        account.scopes = None
        assert google_meet.calendar_scope_state(account) == "unknown"

    def test_a_missing_scope_is_refused_before_any_request(self, db_session, test_user,
                                                           monkeypatch):
        _account(db_session, test_user, OLD_SCOPES)

        def never(*a, **k):
            raise AssertionError("no request may be made without the scope")

        monkeypatch.setattr(google_meet.GoogleMeetAdapter, "create_event", never)
        with pytest.raises(google_meet.GoogleCalendarNotAuthorized) as caught:
            google_meet.create_meet_event(db_session, test_user, summary="x",
                                          start_at=START, end_at=START + timedelta(hours=1))
        assert caught.value.reason == "scope_missing"
        assert caught.value.action == "reconnect_google"

    def test_no_account_is_not_connected(self, db_session, test_user):
        with pytest.raises(google_meet.GoogleCalendarNotAuthorized) as caught:
            google_meet.create_meet_event(db_session, test_user, summary="x",
                                          start_at=START, end_at=START + timedelta(hours=1))
        assert caught.value.reason == "not_connected"

    def test_the_auth_url_asks_for_calendar_incrementally(self):
        from app.integrations.gmail import get_oauth

        query = parse_qs(urlparse(get_oauth().build_auth_url("state-1")).query)
        assert google_meet.CALENDAR_EVENTS_SCOPE in query["scope"][0].split()
        assert query["include_granted_scopes"] == ["true"]
        assert query["access_type"] == ["offline"] and query["prompt"] == ["consent"]

    def test_status_endpoints_report_calendar_access(self, client, db_session, test_user):
        _account(db_session, test_user, OLD_SCOPES)
        assert client.get("/integrations/status").json()["gmail"]["calendar_access"] == "missing"
        assert client.get("/integrations/gmail/status").json()["calendar_access"] == "missing"

    def test_meeting_create_offers_the_reconnect(self, client, db_session, test_user,
                                                 verified_strategy):
        _account(db_session, test_user, OLD_SCOPES)
        resp = client.post("/meetings", json={
            "platform": "google_meet", "title": "Intro",
            "start_at": START.isoformat(), "end_at": (START + timedelta(hours=1)).isoformat(),
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["meeting_url"] is None
        assert body["platform_action"] == "reconnect_google"


# --------------------------------------------------------------------------
# Google Calendar request shapes
# --------------------------------------------------------------------------


def _google(db, user, handler, fake_redis):
    account = _account(db, user, FULL_SCOPES)
    return google_meet.GoogleMeetAdapter(
        db, account, redis=fake_redis, sleep=lambda s: None,
        http=_client(google_meet.GOOGLE_CALENDAR_API_BASE, handler))


class TestGoogleAdapter:
    def test_insert_carries_conference_data_version_and_a_stable_request_id(
            self, db_session, test_user, fake_redis):
        seen: list[httpx.Request] = []

        def handler(request):
            seen.append(request)
            if len(seen) == 1:
                return httpx.Response(503)            # retried by the plumbing
            return httpx.Response(200, json={"id": "evt1", "hangoutLink": "https://meet.google.com/x"})

        event = _google(db_session, test_user, handler, fake_redis).create_event(
            summary="Intro", description=None, start_at=START, end_at=START + timedelta(hours=1))
        assert event["id"] == "evt1"
        first, second = (json.loads(r.content) for r in seen)
        assert seen[1].url.path == "/calendar/v3/calendars/primary/events"
        assert seen[1].url.params["conferenceDataVersion"] == "1"
        assert second["conferenceData"]["createRequest"]["conferenceSolutionKey"]["type"] == \
            "hangoutsMeet"
        # A retry must not mint a second conference.
        assert first["conferenceData"]["createRequest"]["requestId"] == \
            second["conferenceData"]["createRequest"]["requestId"]

    def test_a_pending_conference_is_read_again(self, db_session, test_user, fake_redis):
        def handler(request):
            if request.method == "POST":
                return httpx.Response(200, json={"id": "evt2", "conferenceData": {
                    "createRequest": {"status": {"statusCode": "pending"}}}})
            return httpx.Response(200, json={"id": "evt2", "conferenceData": {"entryPoints": [
                {"entryPointType": "phone", "uri": "tel:+1"},
                {"entryPointType": "video", "uri": "https://meet.google.com/abc"}]}})

        event = _google(db_session, test_user, handler, fake_redis).create_event(
            summary="Intro", description=None, start_at=START, end_at=START + timedelta(hours=1))
        assert google_meet.meet_link(event) == "https://meet.google.com/abc"

    def test_a_403_becomes_the_reconnect_error(self, db_session, test_user, fake_redis):
        adapter = _google(db_session, test_user, lambda r: httpx.Response(403), fake_redis)
        with pytest.raises(google_meet.GoogleCalendarNotAuthorized) as caught:
            adapter.create_event(summary="x", description=None, start_at=START,
                                 end_at=START + timedelta(hours=1))
        assert caught.value.reason == "forbidden"

    def test_the_health_check_uses_a_call_the_granted_scope_permits(self, db_session,
                                                                    test_user, fake_redis):
        paths: list[str] = []

        def handler(request):
            paths.append(request.url.path)
            return httpx.Response(200, json={"items": []})

        assert _google(db_session, test_user, handler, fake_redis).health_check() is True
        assert paths == ["/calendar/v3/calendars/primary/events"]

    def test_delete_accepts_an_empty_204(self, db_session, test_user, fake_redis):
        def handler(request):
            assert request.method == "DELETE" and request.url.params["sendUpdates"] == "none"
            return httpx.Response(204)

        _google(db_session, test_user, handler, fake_redis).delete_event("evt3")


# --------------------------------------------------------------------------
# Zoom
# --------------------------------------------------------------------------


def _zoom(creds, api_handler, token_handler, fake_redis):
    return zoom.ZoomAdapter(
        credentials=creds, redis=fake_redis, sleep=lambda s: None,
        http=_client(zoom.ZOOM_API_BASE, api_handler),
        token_http=httpx.Client(transport=httpx.MockTransport(token_handler)))


CREDS = {"client_id": "cid", "client_secret": "sec", "account_id": "acc", "host_user": "me"}


class TestZoomAdapter:
    def test_admin_store_credentials_win_over_the_environment(self, db_session, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "zoom_oauth_client_id", "env-id")
        monkeypatch.setattr(settings, "zoom_oauth_client_secret", "env-secret")
        monkeypatch.setattr(settings, "zoom_account_id", "env-acc")
        assert zoom.zoom_credentials(db_session)["client_id"] == "env-id"
        for key, value in (("client_id", "db-id"), ("client_secret", "db-secret"),
                           ("account_id", "db-acc"), ("host_user", "host@x.test")):
            credentials.set_system_secret(db_session, "zoom", key, value)
        db_session.commit()
        creds = zoom.zoom_credentials(db_session)
        assert (creds["client_id"], creds["host_user"]) == ("db-id", "host@x.test")

    def test_unconfigured_points_at_the_admin_panel(self, fake_redis):
        adapter = _zoom({"host_user": "me"}, lambda r: httpx.Response(500),
                        lambda r: httpx.Response(500), fake_redis)
        with pytest.raises(zoom.ZoomNotConfigured) as caught:
            adapter.create_meeting(topic="x", start_at=START, duration_minutes=30)
        assert "Admin > Integrations > Zoom" in str(caught.value)
        assert caught.value.action == "configure_zoom"

    def test_token_request_and_meeting_shape(self, fake_redis):
        tokens: list[httpx.Request] = []
        calls: list[httpx.Request] = []

        def token_handler(request):
            tokens.append(request)
            return httpx.Response(200, json={"access_token": "zt", "expires_in": 3600})

        def api_handler(request):
            calls.append(request)
            return httpx.Response(201, json={"id": 123, "join_url": "https://zoom.us/j/123"})

        adapter = _zoom({**CREDS, "host_user": "host@x.test"}, api_handler, token_handler,
                        fake_redis)
        first = adapter.create_meeting(topic="Intro", start_at=START, duration_minutes=30)
        adapter.create_meeting(topic="Again", start_at=START, duration_minutes=30)

        assert first["join_url"] == "https://zoom.us/j/123"
        assert len(tokens) == 1, "the token is cached, not minted per meeting"
        form = parse_qs(tokens[0].content.decode())
        assert form == {"grant_type": ["account_credentials"], "account_id": ["acc"]}
        assert tokens[0].headers["Authorization"].startswith("Basic ")
        assert calls[0].url.path == "/v2/users/host@x.test/meetings"
        body = json.loads(calls[0].content)
        assert body["start_time"] == "2026-09-22T15:00:00Z" and body["type"] == 2
        assert calls[0].headers["Authorization"] == "Bearer zt"

    def test_delete_accepts_an_empty_204(self, fake_redis):
        adapter = _zoom(CREDS, lambda r: httpx.Response(204),
                        lambda r: httpx.Response(200, json={"access_token": "zt"}), fake_redis)
        adapter.delete_meeting("123")


def test_the_plumbing_treats_an_empty_success_body_as_empty(fake_redis):
    class Probe(BaseHttpAdapter):
        provider = "probe"
        base_url = "https://probe.invalid"

    adapter = Probe(redis=fake_redis, sleep=lambda s: None,
                    http=_client("https://probe.invalid", lambda r: httpx.Response(204)))
    assert adapter.call("DELETE", "/thing") == {}
