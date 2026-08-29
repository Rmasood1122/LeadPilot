"""Issue, send and consume signup email-verification links.

FLOW
    signup            -> issue_token()  -> send_verification_email()
    user clicks link  -> consume_token() -> user.email_verified = True
    link expired/lost -> resend endpoint -> issue_token() again

WHAT IS STORED
Only sha256(token). `issue_token` returns the raw value to its caller exactly
once, for the email body, and it is never written anywhere. `consume_token`
hashes the incoming value and looks the hash up. A stolen database dump
therefore contains no usable links. See EmailVerificationToken in
app/db/models.py.

ONE LIVE LINK PER USER
Issuing a token first burns every outstanding one for that user. Without that,
clicking "resend" five times leaves five independently valid links alive for 24
hours each, and revoking access means finding all of them. After this, the most
recently emailed link is the only one that works -- which is also what a user
expects when they ask for a new email.

WHY consume_token RETURNS A STATUS INSTEAD OF RAISING
The four outcomes (verified / already used / expired / unknown) each need a
different message in front of the user, and three of them are ordinary, not
errors: a mail client that prefetches links produces "already used", and a link
clicked on Monday from Friday's email produces "expired". Encoding those as
exceptions would mean the redirect handler catching three exception types to
build three query strings. A status string keeps that decision in one place.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import EmailVerificationToken, User
from app.services.email_sender import send_email

logger = logging.getLogger(__name__)

__all__ = [
    "issue_token",
    "send_link",
    "verification_url",
    "send_verification_email",
    "consume_token",
    "token_hash",
    "VERIFIED",
    "ALREADY_VERIFIED",
    "EXPIRED",
    "INVALID",
]

# consume_token() outcomes.
VERIFIED = "verified"
ALREADY_VERIFIED = "already_verified"
EXPIRED = "expired"
INVALID = "invalid"

# 32 bytes of os.urandom, url-safe base64 -> 43 characters. Guessing one inside
# its 24-hour life is not a realistic attack, which is why the endpoint that
# consumes it is not itself rate limited on the token value.
_TOKEN_BYTES = 32


def token_hash(raw_token: str) -> str:
    """sha256 hex digest -- the only form of a token that is ever persisted."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    """Treat a naive timestamp as UTC.

    SQLite has no timezone-aware storage: a DateTime(timezone=True) column
    round-trips as NAIVE, and comparing that to an aware `now()` raises
    TypeError. PostgreSQL returns it aware. This normalises both so the expiry
    comparison behaves identically on the test database and in production --
    the alternative is an expiry check that passes every test and throws on
    Neon.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def issue_token(db: Session, user: User) -> str:
    """Burn this user's outstanding links, mint a new one, return the RAW token.

    Does not commit -- the caller owns the transaction, so the token row and
    whatever else it is doing (creating the user) land together or not at all.
    """
    now = _now()
    outstanding = db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == user.id,
            EmailVerificationToken.used_at.is_(None),
        )
    ).scalars().all()
    for token_row in outstanding:
        # Stamped rather than deleted: an audit trail of how many links a user
        # needed is worth keeping, and "superseded" and "used" are both
        # non-live states as far as consume_token is concerned.
        token_row.used_at = now

    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    db.add(
        EmailVerificationToken(
            user_id=user.id,
            token_hash=token_hash(raw),
            expires_at=now + timedelta(hours=settings.email_verification_ttl_hours),
        )
    )
    return raw


def verification_url(raw_token: str) -> str:
    """The absolute link that goes in the email.

    Points at the API, not the frontend. The frontend is a static export with
    no server and no route handlers (frontend/next.config.js: output 'export'),
    so it cannot receive a token, call the API and redirect. The API endpoint
    does the work and 302s to the frontend afterwards.

    PUBLIC_BASE_URL must therefore be the PUBLIC origin of the API, not
    localhost, in any environment where a real person clicks the link.
    """
    base = settings.public_base_url.rstrip("/")
    return f"{base}/auth/verify?token={quote(raw_token, safe='')}"


def _render(email: str, link: str) -> tuple[str, str, str]:
    hours = settings.email_verification_ttl_hours
    app = settings.app_name
    subject = f"Verify your {app} account"
    text = (
        f"Welcome to {app}.\n\n"
        f"Confirm this address to activate your account:\n\n"
        f"{link}\n\n"
        f"The link expires in {hours} hours. If it has already expired, sign "
        f'in and press "Resend verification email".\n\n'
        f"If you did not create a {app} account with {email}, ignore this "
        f"message -- no account can be used until this link is clicked.\n"
    )
    html = (
        '<!doctype html><html><body style="font-family:system-ui,-apple-system,'
        'Segoe UI,Roboto,sans-serif;line-height:1.6;color:#111">'
        f'<h2 style="margin:0 0 16px">Welcome to {app}</h2>'
        "<p>Confirm this address to activate your account.</p>"
        f'<p style="margin:24px 0"><a href="{link}" '
        'style="background:#1d4ed8;color:#fff;padding:12px 20px;'
        'border-radius:8px;text-decoration:none;display:inline-block">'
        "Verify my email</a></p>"
        f'<p style="font-size:14px;color:#555">The link expires in {hours} '
        "hours. If it has already expired, sign in and press "
        "&ldquo;Resend verification email&rdquo;.</p>"
        '<p style="font-size:14px;color:#555">Or paste this into your '
        f'browser:<br><span style="word-break:break-all">{link}</span></p>'
        '<hr style="border:none;border-top:1px solid #eee;margin:24px 0">'
        f'<p style="font-size:12px;color:#777">If you did not create a '
        f"{app} account with {email}, ignore this message -- no account can "
        "be used until this link is clicked.</p>"
        "</body></html>"
    )
    return subject, html, text


def send_link(user: User, raw_token: str) -> None:
    """Email an ALREADY-PERSISTED token. Raises EmailSendError on failure.

    Split from issue_token on purpose. The token row has to be committed before
    the message goes out: the two are separate systems, and if the mail is
    delivered while the row is still an uncommitted insert, a click that
    arrives before the commit lands looks up a token that does not exist yet
    and the user is told their brand-new link is invalid. Small window, but it
    is a window that only ever opens for the fastest, most eager users.
    """
    subject, html, text = _render(user.email, verification_url(raw_token))
    send_email(to=user.email, subject=subject, html=html, text=text)


def send_verification_email(db: Session, user: User) -> str:
    """Issue a token and email it in one step. Returns the raw token.

    Convenience for callers that own no transaction of their own. Endpoints
    should prefer issue_token -> commit -> send_link, which closes the window
    described in send_link.

    Raises EmailSendError if the transport fails.
    """
    raw = issue_token(db, user)
    send_link(user, raw)
    return raw


def consume_token(db: Session, raw_token: str) -> tuple[str, User | None]:
    """Validate a clicked link and flip the user to verified.

    Returns (status, user). Does not commit -- the endpoint does, so nothing is
    persisted if the response cannot be built.
    """
    if not raw_token:
        return INVALID, None

    row = db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash(raw_token)
        )
    ).scalars().first()
    if row is None:
        return INVALID, None

    user = db.get(User, row.user_id)
    if user is None:
        # The account was deleted after the email went out.
        return INVALID, None

    if row.used_at is not None:
        # Distinguishing these two matters to the person reading the page:
        # "you are already verified, just sign in" versus "that link is dead,
        # request another".
        return (ALREADY_VERIFIED if user.email_verified else EXPIRED), user

    if _as_aware(row.expires_at) <= _now():
        return EXPIRED, user

    now = _now()
    row.used_at = now
    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = now
    return VERIFIED, user
