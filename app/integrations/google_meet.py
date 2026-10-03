"""Google Calendar adapter — creates an event that carries a Meet link.

There is no "create a Meet link" API. A Google Meet link is produced as a side
effect of inserting a Calendar event with a `conferenceData.createRequest`, and
comes back on the created event. That is why this adapter talks to the
Calendar API and not to anything named Meet.

CREDENTIALS
Reuses the user's already-connected Google account (`gmail_accounts`) and
app/integrations/gmail.py::get_valid_access_token, which handles decryption and
refresh. A second OAuth flow for the same Google account would mean two
refresh tokens for one grant, two expiry clocks, and a user who has to connect
Google twice.

THE SCOPE, AND THE RECONNECT FLOW (Feature 7)
Creating a calendar event needs `calendar.events`, which accounts connected
before the Engagement Hub shipped did not grant. GMAIL_SCOPES includes it, and
the auth URL asks for it with include_granted_scopes=true (incremental
authorization), so a reconnect adds the scope without dropping Gmail's.
The stored grant (`gmail_accounts.scopes`) is checked BEFORE any call:
  granted  -> call Google;
  missing  -> GoogleCalendarNotAuthorized(reason="scope_missing"), no request
              made, action "reconnect_google" -- the UI shows a Reconnect button;
  unknown  -> (no scopes recorded) call Google and let it decide.
A 401/403 from Google is mapped to the same exception (reason="forbidden").

VERIFIED AGAINST CURRENT DOCS (2026-09-13), NEVER CALLED LIVE
developers.google.com/workspace/calendar/api/v3/reference/events/insert and
guides/create-events: POST /calendars/{calendarId}/events; conferenceDataVersion
must be 1 for conference data to persist; sendUpdates accepts all|externalOnly|
none; calendar.events is an accepted scope; the Meet solution type is
"hangoutsMeet"; conference creation can be asynchronous (createRequest status
"pending"), and the join URI is in conferenceData.entryPoints (hangoutLink is
read too). events.list (the health check) accepts calendar.events -- the
previous calendarList health check needed a scope this app never requests, so
it reported every correctly connected account as unhealthy.
Live verification needs credentials: scripts/verify_meeting_platforms.py.

Everything else (retry with backoff, Retry-After, the per-provider circuit
breaker, structured call logging) comes from BaseHttpAdapter for free.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ClientHunterError
from app.db.models import GmailAccount, User
from app.integrations.plumbing import BaseHttpAdapter, ExternalAPIError

logger = logging.getLogger(__name__)

GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
# The broad calendar scope also permits events.insert (same reference page).
_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"
_HANGOUTS_MEET = "hangoutsMeet"
RECONNECT_ACTION = "reconnect_google"


class GoogleCalendarNotAuthorized(ClientHunterError):
    """The connected Google account cannot create calendar events.

    Its own class because the fix is specific and the user can perform it.
    `reason`: not_connected | scope_missing | forbidden. `action` tells the
    client what to offer (a Reconnect button).
    """

    def __init__(self, message: str, reason: str = "forbidden"):
        super().__init__(message)
        self.reason = reason
        self.action = RECONNECT_ACTION


def calendar_scope_state(account: GmailAccount | None) -> str:
    """granted | missing | unknown (no scopes recorded) | not_connected."""
    if account is None:
        return "not_connected"
    scopes = set((account.scopes or "").split())
    if not scopes:
        return "unknown"
    return "granted" if scopes & {CALENDAR_EVENTS_SCOPE, _CALENDAR_SCOPE} else "missing"


def meet_link(event: dict) -> str:
    """The Meet join URL from an event resource, wherever Google put it."""
    if event.get("hangoutLink"):
        return str(event["hangoutLink"])
    for entry in ((event.get("conferenceData") or {}).get("entryPoints") or []):
        if entry.get("entryPointType") == "video" and entry.get("uri"):
            return str(entry["uri"])
    return ""


def _pending(event: dict) -> bool:
    status = (((event.get("conferenceData") or {}).get("createRequest") or {})
              .get("status") or {})
    return status.get("statusCode") == "pending"


class GoogleMeetAdapter(BaseHttpAdapter):
    provider = "google_calendar"
    base_url = GOOGLE_CALENDAR_API_BASE

    def __init__(self, session: Session, account: GmailAccount, **kwargs):
        super().__init__(**kwargs)
        self.session = session
        self.account = account

    def _auth(self) -> dict:
        from app.integrations.gmail import get_valid_access_token  # noqa: PLC0415

        token = get_valid_access_token(self.session, self.account)
        return {"headers": {"Authorization": f"Bearer {token}"}}

    def _call(self, method: str, endpoint: str, **kwargs) -> dict:
        try:
            return self.call(method, endpoint, **kwargs)
        except ExternalAPIError as exc:
            if exc.status in (401, 403):
                raise GoogleCalendarNotAuthorized(
                    "the connected Google account is not authorised to manage "
                    "calendar events. Reconnect Google in Settings to grant "
                    "calendar access, or pick a different meeting platform.",
                    reason="forbidden",
                ) from exc
            raise

    def create_event(self, *, summary: str, description: str | None,
                     start_at: datetime, end_at: datetime,
                     attendee_emails: list[str] | None = None,
                     with_meet_link: bool = True) -> dict:
        """Insert an event on the account's primary calendar. Returns the event
        resource, re-read once if Google reported the conference as pending."""
        body: dict = {
            "summary": summary[:1000],
            "description": (description or "")[:8000] or None,
            # RFC3339 with an offset. `timeZone` is deliberately omitted: the
            # instant is already unambiguous, and sending a zone alongside an
            # offset is how an event lands an hour out when the two disagree.
            "start": {"dateTime": start_at.isoformat()},
            "end": {"dateTime": end_at.isoformat()},
        }
        if attendee_emails:
            body["attendees"] = [{"email": e} for e in attendee_emails if e]
        if with_meet_link:
            body["conferenceData"] = {
                "createRequest": {
                    # Generated ONCE per event: BaseHttpAdapter.call() retries
                    # 5xx with this same body, and Google dedupes conference
                    # creation on requestId -- a per-attempt id could mint two
                    # Meet links for one event.
                    "requestId": str(uuid.uuid4()),
                    "conferenceSolutionKey": {"type": _HANGOUTS_MEET},
                }
            }

        event = self._call(
            "POST", "/calendars/primary/events",
            # conferenceDataVersion=1 or Google ignores conferenceData.
            params={"conferenceDataVersion": 1, "sendUpdates": "all"},
            json_body=body,
        )
        if with_meet_link and not meet_link(event) and _pending(event) and event.get("id"):
            event = self.get_event(str(event["id"]))
        return event

    def get_event(self, event_id: str) -> dict:
        return self._call("GET", f"/calendars/primary/events/{event_id}")

    def delete_event(self, event_id: str, *, notify: bool = False) -> None:
        self._call("DELETE", f"/calendars/primary/events/{event_id}",
                   params={"sendUpdates": "all" if notify else "none"})

    def health_check(self) -> bool:
        if self.breaker.is_open():
            return False
        try:
            self.call("GET", "/calendars/primary/events", params={"maxResults": 1})
            return True
        except Exception:  # noqa: BLE001 — a health check reports, never raises
            return False


def create_meet_event(session: Session, user: User, *, summary: str,
                      start_at: datetime, end_at: datetime,
                      description: str | None = None,
                      attendee_emails: list[str] | None = None) -> dict:
    """{"join_url", "external_event_id", "html_link"} for a new Meet event.

    Raises GoogleCalendarNotAuthorized -- before any request -- when no Google
    account is connected or the stored grant lacks calendar access.
    """
    from app.integrations.gmail import GmailNotConnected, get_account  # noqa: PLC0415

    try:
        account = get_account(session, user)
    except GmailNotConnected as exc:
        raise GoogleCalendarNotAuthorized(
            "no Google account is connected. Connect Google in Settings, or "
            "create the meeting with a custom link instead.",
            reason="not_connected",
        ) from exc
    if calendar_scope_state(account) == "missing":
        raise GoogleCalendarNotAuthorized(
            "your Google connection predates calendar access. Reconnect Google "
            "in Settings to create Meet links, or use a custom link.",
            reason="scope_missing",
        )

    event = GoogleMeetAdapter(session, account).create_event(
        summary=summary, description=description,
        start_at=start_at, end_at=end_at, attendee_emails=attendee_emails,
    )
    join_url = meet_link(event)
    if not join_url:
        # The event exists but has no conference attached -- Meet disabled by a
        # Workspace policy, or creation still pending after one re-read.
        logger.warning("google calendar event %s created without a Meet link",
                       event.get("id"))
    return {
        "join_url": join_url,
        "external_event_id": str(event.get("id") or "")[:200],
        "html_link": event.get("htmlLink"),
    }
