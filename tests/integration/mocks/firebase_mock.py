"""
Firebase Cloud Messaging (FCM) mock.

Captures every push notification so tests can assert:
  - the lead owner received meeting_booked / new_reply
  - the strategy owner received strategy_ready / needs_review / campaign_paused
  - admins received the circuit_opened and template-status notifications

WHY THIS IS NOT A respx MOCK
----------------------------
It used to register respx routes on https://fcm.googleapis.com and could
never have captured anything. respx patches **httpx**, and the send path this
application uses is:

    notifications.send_to_device()
      -> firebase_admin.messaging.send(message)
        -> _MessagingService._client            = _http_client.JsonHttpClient
          -> _http_client.HttpClient.__init__   = google.auth.transport.requests
                                                  .AuthorizedSession(credential)

i.e. **requests**, not httpx. (firebase-admin 7.x does ship an httpx client,
`HttpxAsyncClient`, but only `send_each_async()` uses it - an async batch API
with a different signature and `dry_run=True` by default. Switching production
to it purely so respx could observe the traffic would change real sending
behaviour to suit a test, so it was rejected.)

So the interception happens at the SDK boundary the application actually
calls, which is also the pattern the root suite already uses for Firebase
(tests/test_notifications.py installs a MagicMock into sys.modules):

  * `firebase_admin.messaging.send` is replaced with a recorder. Everything
    above it stays REAL - `messaging.Message`, `messaging.Notification` and
    `messaging.AndroidConfig` are still constructed and validated by the SDK,
    so a malformed payload still fails the test rather than being papered over.
  * `notifications._get_firebase_app` is stubbed, because the only thing left
    below the recorder is credential parsing: `credentials.Certificate()` wants
    a real service-account JSON with a real RSA key, and google-auth would mint
    an OAuth token over the network. That is Google's code, not this
    application's, and nothing under test depends on it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SentNotification:
    """One captured push, flattened for assertions."""
    token: str
    title: str | None
    body: str | None
    data: dict[str, str] = field(default_factory=dict)

    @property
    def deep_link(self) -> str | None:
        return self.data.get("deepLink")


@dataclass
class FCMCallCapture:
    notifications: list[SentNotification] = field(default_factory=list)


_capture = FCMCallCapture()


def get_capture() -> FCMCallCapture:
    return _capture


def reset_capture() -> None:
    _capture.notifications.clear()


def get_all_notifications() -> list[SentNotification]:
    """Every push captured during the test."""
    return list(_capture.notifications)


def notifications_for_tokens(tokens) -> list[SentNotification]:
    """Pushes delivered to any of `tokens` - the tenancy assertion helper.

    Tests register a device token per user and then assert that a notification
    reached exactly the owner's token and no one else's.
    """
    wanted = set(tokens)
    return [n for n in _capture.notifications if n.token in wanted]


def _record(message: Any) -> str:
    """Stand-in for firebase_admin.messaging.send()."""
    note = getattr(message, "notification", None)
    _capture.notifications.append(SentNotification(
        token=getattr(message, "token", None),
        title=getattr(note, "title", None),
        body=getattr(note, "body", None),
        data=dict(getattr(message, "data", None) or {}),
    ))
    return f"projects/test/messages/{len(_capture.notifications)}"


def install(monkeypatch) -> FCMCallCapture:
    """Patch the FCM send path for one test. Returns the capture."""
    from firebase_admin import messaging

    from app.services import notifications as notif

    reset_capture()
    monkeypatch.setattr(messaging, "send", _record)
    monkeypatch.setattr(notif, "_get_firebase_app", lambda: object())
    return _capture


def register(router=None) -> None:
    """Kept so `all_mocks` can call it uniformly.

    Registration is per-test and needs monkeypatch, so the real work happens in
    install(); this only clears the capture. It takes and ignores the respx
    router because the other mocks in this package are registered that way.
    """
    reset_capture()
