"""F-OPS-02 — a Calendly webhook must be FRESH as well as correctly signed.

The signature covers "<t>.<body>", and `t` was never looked at. A delivery
captured once could be replayed for ever; the only thing standing in the way
was the event-id dedupe table.

Now: `t` older than CALENDLY_WEBHOOK_TOLERANCE_SECONDS (default 180, the
tolerance zone Calendly's own signature docs demonstrate) is
refused, and so is `t` more than 300 seconds in the future. The clock is
injectable (app.integrations.calendly._now), so nothing here sleeps or reads
the wall clock.
"""

import hashlib
import hmac
import json

import pytest
from sqlalchemy import select

from app.config import settings
from app.db import models as m
from app.integrations import calendly
from app.integrations.calendly import verify_webhook_signature

KEY = "freshness-signing-key"
NOW = 1_790_000_000          # the pinned "current time", in Unix seconds


def _header(body: str, ts, key: str = KEY) -> str:
    sig = hmac.new(key.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def _payload(uri: str = "https://api.calendly.com/scheduled_events/EV9/invitees/INV9") -> dict:
    return {"event": "invitee.created",
            "payload": {"email": "nobody@freshness.test", "uri": uri}}


@pytest.fixture()
def clock(monkeypatch):
    monkeypatch.setattr(settings, "calendly_webhook_signing_key", KEY)
    # raising=False so this module can also be run against code that has no
    # injectable clock yet (the pre-fix run), where it must FAIL, not error.
    monkeypatch.setattr(calendly, "_now", lambda: float(NOW), raising=False)
    return NOW


def _post(client, ts, payload: dict | None = None):
    body = json.dumps(payload or _payload())
    return client.post("/webhooks/calendly", content=body,
                       headers={"Calendly-Webhook-Signature": _header(body, ts),
                                "Content-Type": "application/json"})


def _claimed(db_session) -> list:
    return db_session.execute(select(m.ProcessedWebhook).where(
        m.ProcessedWebhook.provider == "calendly")).scalars().all()


class TestTheDefault:
    def test_the_tolerance_defaults_to_three_minutes(self):
        """The window Calendly's own signature documentation demonstrates."""
        assert settings.calendly_webhook_tolerance_seconds == 180

    def test_the_future_allowance_is_five_minutes(self):
        assert calendly.FUTURE_SKEW_SECONDS == 300


class TestVerifyFunction:
    """The pure function, with the clock passed in."""

    BODY = b'{"event": "invitee.created"}'

    def _check(self, ts, **kwargs) -> bool:
        return verify_webhook_signature(self.BODY, _header(self.BODY.decode(), ts),
                                        KEY, now=NOW, **kwargs)

    def test_a_fresh_timestamp_is_accepted(self):
        assert self._check(NOW) is True
        assert self._check(NOW - 60) is True

    def test_exactly_at_the_tolerance_is_accepted(self):
        assert self._check(NOW - 180) is True

    def test_comfortably_past_the_tolerance_is_rejected(self):
        assert self._check(NOW - 31 * 60) is False

    def test_one_second_past_the_tolerance_is_rejected(self):
        assert self._check(NOW - 181) is False

    def test_slightly_in_the_future_is_accepted(self):
        """Clocks drift; five minutes is allowed."""
        assert self._check(NOW + 300) is True

    def test_more_than_five_minutes_in_the_future_is_rejected(self):
        assert self._check(NOW + 301) is False
        assert self._check(NOW + 3600) is False

    def test_a_timestamp_that_is_not_a_number_is_rejected(self):
        assert self._check("yesterday") is False
        assert self._check("") is False

    def test_the_tolerance_can_be_overridden(self):
        assert self._check(NOW - 120, tolerance_seconds=60) is False
        assert self._check(NOW - 30, tolerance_seconds=60) is True

    def test_a_wrong_signature_is_rejected_however_fresh(self):
        header = _header(self.BODY.decode(), NOW, key="some-other-key")
        assert verify_webhook_signature(self.BODY, header, KEY, now=NOW) is False


class TestTheWebhook:
    def test_a_fresh_delivery_is_accepted(self, leads_client, db_session, clock):
        response = _post(leads_client, clock - 5)
        assert response.status_code == 200, response.text
        assert len(_claimed(db_session)) == 1

    def test_a_thirty_one_minute_old_delivery_is_rejected_and_writes_nothing(
            self, leads_client, db_session, clock):
        response = _post(leads_client, clock - 31 * 60)
        assert response.status_code == 401, response.text
        assert _claimed(db_session) == []

    def test_a_delivery_from_the_future_is_rejected_and_writes_nothing(
            self, leads_client, db_session, clock):
        response = _post(leads_client, clock + 6 * 60)
        assert response.status_code == 401, response.text
        assert _claimed(db_session) == []

    def test_the_tolerance_setting_is_what_the_webhook_uses(
            self, leads_client, db_session, clock, monkeypatch):
        monkeypatch.setattr(settings, "calendly_webhook_tolerance_seconds", 60)
        assert _post(leads_client, clock - 120).status_code == 401
        assert _post(leads_client, clock - 30).status_code == 200

    def test_an_identical_replay_inside_the_window_is_still_a_no_op(
            self, leads_client, db_session, clock):
        first = _post(leads_client, clock - 5)
        second = _post(leads_client, clock - 5)
        assert first.status_code == 200 and second.status_code == 200
        assert second.json() == {"ok": True, "duplicate": True}
        assert len(_claimed(db_session)) == 1

    def test_a_captured_delivery_replayed_after_the_window_is_refused(
            self, leads_client, db_session, clock, monkeypatch):
        """The attack this closes: same bytes, same valid signature, later."""
        payload = _payload("https://api.calendly.com/scheduled_events/EV7/invitees/INV7")
        assert _post(leads_client, clock, payload).status_code == 200

        monkeypatch.setattr(calendly, "_now", lambda: float(NOW + 2 * 3600),
                            raising=False)
        replay = _post(leads_client, clock, payload)
        assert replay.status_code == 401, replay.text
        assert len(_claimed(db_session)) == 1
