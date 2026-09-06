"""Google Calendar adapter — creates an event that carries a Meet link.

There is no "create a Meet link" API. A Google Meet link is produced as a side
effect of inserting a Calendar event with a `conferenceData.createRequest`, and
comes back on the created event as `hangoutLink`. That is why this adapter
talks to the Calendar API and not to anything named Meet.

CREDENTIALS
Reuses the user's already-connected Google account (`gmail_accounts`) and
app/integrations/gmail.py::get_valid_access_token, which handles decryption and
refresh. A second OAuth flow for the same Google account would mean two
refresh tokens for one grant, two expiry clocks, and a user who has to connect
Google twice.

THE SCOPE CAVEAT, STATED PLAINLY
Creating a calendar event needs `calendar.events`, which accounts connected
before this feature shipped did not grant. GMAIL_SCOPES now includes it, so
anyone connecting from here on gets it — but an existing account's token does
not gain a scope retroactively. Google answers 403 in that case, and
`create_meet_event` translates that specific failure into
GoogleCalendarNotAuthorized with a message naming the reconnect URL, rather
than surfacing a raw "insufficient permissions" the user cannot act on.

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

# TODO: verify against current Google Calendar API docs (v3 events.insert).
GOOGLE_CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"

# The conference solution key that produces a Meet link.
# TODO: verify against current Google Calendar API docs.
_HANGOUTS_MEET = "hangoutsMeet"


class GoogleCalendarNotAuthorized(ClientHunterError):
    """The connected Google account cannot create calendar events.

    Its own class rather than a generic error because the fix is specific and
    the user can perform it: reconnect Google so the grant includes
    calendar.events.
    """


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

    def create_event(self, *, summary: str, description: str | None,
                     start_at: datetime, end_at: datetime,
                     attendee_emails: list[str] | None = None,
                     with_meet_link: bool = True) -> dict:
        """Insert an event on the account's primary calendar.

        Returns the raw event resource. `hangoutLink` is present when
        `with_meet_link` is true and Google honoured the create request.
        """
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
                    # Google dedupes on this: retrying the same requestId
                    # returns the same conference instead of minting a second
                    # one. BaseHttpAdapter.call() retries 5xx, so a request id
                    # that changed per attempt could create two Meet links for
                    # one event.
                    "requestId": str(uuid.uuid4()),
                    "conferenceSolutionKey": {"type": _HANGOUTS_MEET},
                }
            }

        try:
            return self.call(
                "POST", "/calendars/primary/events",
                # Required, or Google silently ignores conferenceData and the
                # event comes back with no hangoutLink and no error.
                # TODO: verify against current Google Calendar API docs.
                params={"conferenceDataVersion": 1, "sendUpdates": "all"},
                json_body=body,
            )
        except ExternalAPIError as exc:
            if exc.status in (401, 403):
                raise GoogleCalendarNotAuthorized(
                    "the connected Google account is not authorised to create "
                    "calendar events. Reconnect Google at "
                    "/integrations/gmail/auth-url to grant calendar access, "
                    "or pick a different meeting platform."
                ) from exc
            raise

    def health_check(self) -> bool:
        if self.breaker.is_open():
            return False
        try:
            self.call("GET", "/users/me/calendarList", params={"maxResults": 1})
            return True
        except Exception:  # noqa: BLE001 — a health check reports, never raises
            return False


def create_meet_event(session: Session, user: User, *, summary: str,
                      start_at: datetime, end_at: datetime,
                      description: str | None = None,
                      attendee_emails: list[str] | None = None) -> dict:
    """{"join_url", "external_event_id"} for a new Meet-backed event.

    Raises GoogleCalendarNotAuthorized when the user has no connected Google
    account at all, for the same reason as the scope case: it is a condition
    the user can fix, and the message says how.
    """
    from app.integrations.gmail import GmailNotConnected, get_account  # noqa: PLC0415

    try:
        account = get_account(session, user)
    except GmailNotConnected as exc:
        raise GoogleCalendarNotAuthorized(
            "no Google account is connected for this user. Connect one at "
            "/integrations/gmail/auth-url, or create the meeting with a "
            "custom link instead."
        ) from exc

    event = GoogleMeetAdapter(session, account).create_event(
        summary=summary, description=description,
        start_at=start_at, end_at=end_at, attendee_emails=attendee_emails,
    )
    join_url = event.get("hangoutLink") or ""
    if not join_url:
        # The event exists but has no conference attached — an account with
        # Meet disabled by a Workspace policy. Reported rather than swallowed:
        # a meeting row with no join URL is a meeting nobody can attend.
        logger.warning("google calendar event %s created without a Meet link",
                       event.get("id"))
    return {
        "join_url": join_url,
        "external_event_id": str(event.get("id") or "")[:200],
        "html_link": event.get("htmlLink"),
    }
