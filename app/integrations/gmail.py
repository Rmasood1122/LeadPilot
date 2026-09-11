"""Gmail adapter — Milestone 3.

Chunk 1 (this file's current state): OAuth 2.0 per user — auth URL,
code exchange, ENCRYPTED token storage, automatic refresh — plus the
OutreachChannel skeleton and health check.
Chunk 3 implements send(); Chunk 4 implements fetch_replies()/status().

Google OAuth endpoints below are the documented stable ones; anything not
100% certain is marked `# TODO: verify against current Gmail API docs`.
Reuses the M2 plumbing (retry/backoff, structured logging, circuit
breaker) for all Gmail API calls via BaseHttpAdapter.
"""

import base64
import logging
import uuid
from email.message import EmailMessage
from email.utils import parseaddr
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import GmailAccount, User
from app.integrations.outreach_base import (
    InboundMessage,
    OutboundMessage,
    OutreachChannel,
    SendResult,
    register_channel,
)
from app.integrations.plumbing import BaseHttpAdapter
from app.services import crypto

logger = logging.getLogger(__name__)

# TODO: verify exact scope strings against current Gmail API docs
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    # Engagement Hub: app/integrations/google_meet.py creates a Calendar event
    # (which is the only way to mint a Google Meet link) on this same grant,
    # rather than putting the user through a second Google consent flow for
    # the same account.
    #
    # An account connected BEFORE this line existed does not gain the scope
    # retroactively -- Google answers 403, and google_meet.py turns that one
    # status into GoogleCalendarNotAuthorized with a message telling the user
    # to reconnect. Adding it here is what makes every new connection work
    # without that step.
    "https://www.googleapis.com/auth/calendar.events",
    # Feature Group 7: "Log Meeting Outcome" saves the follow-up email as a
    # Gmail DRAFT for the user to review, which gmail.send cannot do. Same
    # retroactivity caveat as calendar.events: an older grant answers 403, and
    # create_draft() turns that into GmailScopeMissing ("reconnect Gmail").
    "https://www.googleapis.com/auth/gmail.compose",
]

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"  # TODO: verify against current Gmail API docs


class GmailNotConnected(Exception):
    pass


class ChannelNotReady(NotImplementedError):
    """Raised by capabilities that land in a later M3 chunk."""


# --------------------------------------------------------------------------
# Signed state for the OAuth round-trip (encrypts the user id + a nonce)
# --------------------------------------------------------------------------


def make_state(user_id: uuid.UUID) -> str:
    return crypto.encrypt_json({"user_id": str(user_id), "nonce": uuid.uuid4().hex})


def parse_state(state: str) -> uuid.UUID:
    try:
        return uuid.UUID(crypto.decrypt_json(state)["user_id"])
    except Exception as exc:
        raise ValueError("invalid or tampered OAuth state") from exc


# --------------------------------------------------------------------------
# OAuth flow
# --------------------------------------------------------------------------


class GmailOAuth:
    """Auth URL generation, code exchange, token refresh (plain OAuth 2.0)."""

    def __init__(self, http: httpx.Client | None = None):
        self.http = http or httpx.Client(timeout=30.0)

    def build_auth_url(self, state: str) -> str:
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",   # required for a refresh_token
            "prompt": "consent",        # re-consent so refresh_token is always returned
            "state": state,
        }
        return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        resp = self.http.post(GOOGLE_TOKEN_ENDPOINT, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": settings.google_redirect_uri,
        })
        resp.raise_for_status()
        return resp.json()  # access_token, refresh_token, expires_in, scope, ...

    def refresh(self, refresh_token: str) -> dict:
        resp = self.http.post(GOOGLE_TOKEN_ENDPOINT, data={
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        return resp.json()  # access_token, expires_in (no new refresh_token usually)

    def fetch_profile_email(self, access_token: str) -> str | None:
        """The connected mailbox's address.
        # TODO: verify against current Gmail API docs (users.getProfile)"""
        try:
            resp = self.http.get(
                f"{GMAIL_API_BASE}/users/me/profile",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json().get("emailAddress")
        except httpx.HTTPError:
            logger.warning("could not fetch Gmail profile email", exc_info=True)
            return None


def get_oauth() -> GmailOAuth:
    """Factory the API layer uses — tests monkeypatch THIS function."""
    return GmailOAuth()


# --------------------------------------------------------------------------
# Encrypted token storage + automatic refresh
# --------------------------------------------------------------------------


def _expiry_from(tokens: dict) -> datetime | None:
    expires_in = tokens.get("expires_in")
    if expires_in is None:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))


def store_tokens(session: Session, user: User, tokens: dict,
                 oauth: GmailOAuth | None = None) -> GmailAccount:
    """Create/update the user's GmailAccount with ENCRYPTED tokens."""
    oauth = oauth or get_oauth()
    account = session.query(GmailAccount).filter_by(user_id=user.id).one_or_none()
    if account is None:
        account = GmailAccount(user_id=user.id)
        session.add(account)

    existing: dict = {}
    if account.token_ciphertext:
        try:
            existing = crypto.decrypt_json(account.token_ciphertext)
        except ValueError:
            existing = {}
    # Google omits refresh_token on re-auth — never lose the one we have.
    merged = {**existing, **{k: v for k, v in tokens.items() if v is not None}}
    if "refresh_token" not in merged:
        raise GmailNotConnected(
            "Google did not return a refresh_token — re-run the auth flow "
            "(prompt=consent) so offline access is granted."
        )

    account.token_ciphertext = crypto.encrypt_json(merged)
    account.token_expires_at = _expiry_from(tokens) or account.token_expires_at
    account.scopes = tokens.get("scope") or account.scopes or " ".join(GMAIL_SCOPES)
    if tokens.get("access_token"):
        account.email_address = (
            oauth.fetch_profile_email(tokens["access_token"]) or account.email_address
        )
    session.commit()
    return account


def get_valid_access_token(session: Session, account: GmailAccount,
                           oauth: GmailOAuth | None = None) -> str:
    """Return a live access token, refreshing (and re-encrypting) if it
    expires within the configured leeway."""
    oauth = oauth or get_oauth()
    tokens = crypto.decrypt_json(account.token_ciphertext)

    leeway = timedelta(seconds=settings.gmail_token_refresh_leeway_seconds)
    expires_at = account.token_expires_at
    needs_refresh = (
        not tokens.get("access_token")
        or expires_at is None
        or expires_at <= datetime.now(timezone.utc) + leeway
    )
    if needs_refresh:
        refreshed = oauth.refresh(tokens["refresh_token"])
        tokens = {**tokens, **{k: v for k, v in refreshed.items() if v is not None}}
        account.token_ciphertext = crypto.encrypt_json(tokens)
        account.token_expires_at = _expiry_from(refreshed) or account.token_expires_at
        session.commit()
        logger.info("gmail access token refreshed for account %s", account.id)

    return tokens["access_token"]


def get_account(session: Session, user: User) -> GmailAccount:
    account = session.query(GmailAccount).filter_by(user_id=user.id).one_or_none()
    if account is None:
        raise GmailNotConnected(f"user {user.email} has no connected Gmail account")
    return account


# --------------------------------------------------------------------------
# The channel (skeleton — send lands in Chunk 3, replies in Chunk 4)
# --------------------------------------------------------------------------


@register_channel
class GmailChannel(BaseHttpAdapter, OutreachChannel):
    channel = "email"
    provider = "gmail"
    base_url = GMAIL_API_BASE

    def __init__(self, account: GmailAccount, session: Session,
                 oauth: GmailOAuth | None = None, **kwargs):
        super().__init__(**kwargs)
        self.account = account
        self.session = session
        self.oauth = oauth or get_oauth()

    def _auth(self) -> dict:
        token = get_valid_access_token(self.session, self.account, self.oauth)
        return {"headers": {"Authorization": f"Bearer {token}"}}

    # ---- sending ---------------------------------------------------------
    def send(self, message: OutboundMessage) -> SendResult:
        """Send one RFC-2822 message via the Gmail API. Compliance headers
        (List-Unsubscribe etc.) arrive pre-built in message.headers — this
        channel only transports them."""
        mime = EmailMessage()
        mime["From"] = self.account.email_address or "me"
        mime["To"] = message.to_address
        if message.subject:
            mime["Subject"] = message.subject
        for name, value in (message.headers or {}).items():
            mime[name] = value
        mime.set_content(message.body)
        # Feature Group 3: the engine may supply an HTML twin (open pixel).
        # Plain text stays the first part, so text-only clients and spam
        # filters see exactly the message that was written.
        html_part = (message.metadata or {}).get("html_body")
        if html_part:
            mime.add_alternative(html_part, subtype="html")

        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        payload: dict = {"raw": raw}
        if message.thread_ref:
            payload["threadId"] = message.thread_ref  # TODO: verify against current Gmail API docs

        try:
            # TODO: verify against current Gmail API docs (users.messages.send)
            data = self.call("POST", "/users/me/messages/send", json_body=payload)
        except Exception as exc:
            status_code = getattr(exc, "status", None)
            return SendResult(
                ok=False,
                error=str(exc),
                permanent_failure=status_code in (400, 403),
                raw={"status": status_code},
            )
        return SendResult(
            ok=True,
            provider_message_id=data.get("id"),
            thread_ref=data.get("threadId"),
            raw=data,
        )

    # ---- inbound ----------------------------------------------------------
    def fetch_replies(self, since: datetime | None = None) -> list[InboundMessage]:
        """New inbound messages for this mailbox. Uses a Gmail search query
        window; message payloads are fetched individually and parsed
        tolerantly. # TODO: verify against current Gmail API docs
        (users.messages.list / users.messages.get, q syntax)."""
        query = "in:inbox -from:me"
        if since is not None:
            query += f" after:{int(since.timestamp())}"  # TODO: verify epoch support in q
        listing = self.call("GET", "/users/me/messages",
                            params={"q": query, "maxResults": 50})
        out: list[InboundMessage] = []
        for stub in listing.get("messages") or []:
            data = self.call("GET", f"/users/me/messages/{stub['id']}",
                             params={"format": "full"})
            out.append(self._parse_inbound(data))
        return out

    def status(self, provider_message_id: str) -> dict:
        data = self.call("GET", f"/users/me/messages/{provider_message_id}",
                         params={"format": "metadata"})
        return {"labelIds": data.get("labelIds", []), "threadId": data.get("threadId")}

    @staticmethod
    def _parse_inbound(data: dict) -> InboundMessage:
        payload = data.get("payload") or {}
        headers = {h.get("name", "").lower(): h.get("value", "")
                   for h in payload.get("headers") or []}

        def _decode(part: dict) -> str:
            body = (part.get("body") or {}).get("data")
            if not body:
                return ""
            try:
                return base64.urlsafe_b64decode(body + "===").decode(errors="replace")
            except Exception:
                return ""

        text = ""
        if payload.get("mimeType", "").startswith("text/"):
            text = _decode(payload)
        for part in payload.get("parts") or []:
            if part.get("mimeType") == "text/plain":
                text = _decode(part) or text
                break
        if not text:
            text = data.get("snippet", "")

        _, from_addr = parseaddr(headers.get("from", ""))
        _, to_addr = parseaddr(headers.get("to", ""))
        return InboundMessage(
            provider_message_id=data.get("id", ""),
            thread_ref=data.get("threadId"),
            from_address=from_addr or headers.get("from", ""),
            to_address=to_addr or None,
            subject=headers.get("subject"),
            body=text,
            received_at=None,
            raw={"labelIds": data.get("labelIds", [])},
        )

    # ---- live now --------------------------------------------------------
    def health_check(self) -> bool:
        if self.breaker.is_open():
            return False
        try:
            # TODO: verify against current Gmail API docs (users.getProfile)
            self.call("GET", "/users/me/profile")
            return True
        except Exception:
            return False


# --------------------------------------------------------------------------
# Drafts (Feature Group 7 — the post-meeting follow-up)
# --------------------------------------------------------------------------
#
# Deliberately NOT routed through GmailChannel/BaseHttpAdapter. The channel is
# the OUTREACH transport: its circuit breaker, caps and send windows govern
# cold email, and a user saving one draft for a prospect they just met is not
# outreach volume. Sharing the breaker would let a burst of draft failures
# pause the user's campaigns, and vice versa.


class GmailScopeMissing(GmailNotConnected):
    """The grant predates gmail.compose — the user must reconnect Gmail."""


def _gmail_http() -> httpx.Client:
    """Factory tests monkeypatch."""
    return httpx.Client(base_url=GMAIL_API_BASE, timeout=30.0)


def _raw_message(from_addr: str | None, to: str, subject: str, body: str) -> str:
    mime = EmailMessage()
    mime["From"] = from_addr or "me"
    mime["To"] = to
    mime["Subject"] = subject
    mime.set_content(body)
    return base64.urlsafe_b64encode(mime.as_bytes()).decode()


def _drafts_call(session: Session, account: GmailAccount, method: str, path: str,
                 payload: dict, oauth: GmailOAuth | None = None) -> dict:
    token = get_valid_access_token(session, account, oauth)
    with _gmail_http() as http:
        resp = http.request(method, path, json=payload,
                            headers={"Authorization": f"Bearer {token}"})
    if resp.status_code == 403:
        raise GmailScopeMissing(
            "Gmail refused to create a draft (403). This connection was made "
            "before draft access was requested -- reconnect Gmail in Settings."
        )
    resp.raise_for_status()
    return resp.json()


def create_draft(session: Session, account: GmailAccount, *, to: str,
                 subject: str, body: str, thread_ref: str | None = None,
                 oauth: GmailOAuth | None = None) -> dict:
    """users.drafts.create. Returns {"id": draftId, "message": {...}}.
    # TODO: verify against current Gmail API docs (users.drafts.create)"""
    message: dict = {"raw": _raw_message(account.email_address, to, subject, body)}
    if thread_ref:
        message["threadId"] = thread_ref
    return _drafts_call(session, account, "POST", "/users/me/drafts",
                        {"message": message}, oauth)


def update_draft(session: Session, account: GmailAccount, draft_id: str, *,
                 to: str, subject: str, body: str,
                 thread_ref: str | None = None,
                 oauth: GmailOAuth | None = None) -> dict:
    """users.drafts.update (full replace)."""
    message: dict = {"raw": _raw_message(account.email_address, to, subject, body)}
    if thread_ref:
        message["threadId"] = thread_ref
    return _drafts_call(session, account, "PUT", f"/users/me/drafts/{draft_id}",
                        {"id": draft_id, "message": message}, oauth)


def send_draft(session: Session, account: GmailAccount, draft_id: str,
               oauth: GmailOAuth | None = None) -> dict:
    """users.drafts.send. Returns the sent Message resource."""
    return _drafts_call(session, account, "POST", "/users/me/drafts/send",
                        {"id": draft_id}, oauth)
