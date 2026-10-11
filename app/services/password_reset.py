"""Forgotten-password reset: issue, email and redeem single-use reset links.

FLOW
    POST /auth/password-reset/request  -> eligible?  -> issue_token() -> commit
                                          -> send_link() (after the response)
    user opens the link (frontend /reset-password#token=...)
    POST /auth/password-reset/confirm  -> redeem() -> new hash, every session
                                          revoked, audit row -> commit

Modelled on app/services/email_verification.py (same token size, same
hash-only storage, same "burn the outstanding ones first" rule). The
differences are all because a reset link is worth more to an attacker than a
verification link -- it sets the password:

  * 60-minute life (PASSWORD_RESET_TTL_MINUTES), not 24 hours.
  * Redeeming one burns EVERY outstanding reset link for the account and
    signs the account out everywhere, exactly as change-password does
    (app/api/auth.py _sign_out_everywhere): every refresh session revoked,
    users.password_changed_at stamped so every older refresh or access token
    is refused, and every personal API key revoked.
  * Redeeming is a conditional UPDATE (one winner per link), and issuing
    locks the account row, so concurrent requests cannot mint two live links
    or spend one link twice. At most DAILY_EMAIL_LIMIT emails per 24 hours.
  * The link points at the FRONTEND, with the token in the URL FRAGMENT
    (#token=...). A fragment is never sent to any server -- not to the static
    host, not to a CDN access log, not in a Referer header -- so the token
    only ever travels in the confirm request's JSON body. (Verification links
    point at the API because a GET there can finish the job; a reset needs a
    form, so it has to land on a page.)

WHO CAN RESET
An account with a password that is not suspended. Never:
  * an unknown address (nothing to send to -- and the caller is not told);
  * a passwordless pre-auth row: it has never been claimed, and letting a
    reset claim it would side-step the sign-up policy (closed sign-up,
    allowed domains) that POST /auth/signup enforces;
  * a suspended account, checked at request AND at redeem time, so a
    suspension that lands between the two still wins.
Deleted accounts are covered by the foreign key: deleting the user deletes
its tokens (ON DELETE CASCADE, plus the ORM cascade on User), so their links
are unknown tokens. This product has no soft-delete/tombstone for users.

NO ENUMERATION
The request endpoint answers the same 200 for every address. Rate limits are
keyed on the IP and on the address itself, so a 429 is also the same for an
address with or without an account. The email is sent after the response
(FastAPI BackgroundTasks), so a slow mail relay does not make "has an account"
measurably slower than "has none".
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import PasswordResetToken, User
from app.services.email_sender import send_email

logger = logging.getLogger(__name__)

__all__ = [
    "RESET",
    "INVALID",
    "EXPIRED",
    "INELIGIBLE",
    "RESEND_COOLDOWN_SECONDS",
    "DAILY_EMAIL_LIMIT",
    "eligible",
    "find_eligible",
    "issue_token",
    "reset_url",
    "send_link",
    "redeem",
    "token_hash",
]

# redeem() outcomes.
RESET = "reset"
INVALID = "invalid"        # unknown, already used, or superseded
EXPIRED = "expired"
INELIGIBLE = "ineligible"  # the account became suspended / passwordless

_TOKEN_BYTES = 32  # 43 url-safe characters, same as verification links

# A second request for the same account inside this window sends nothing.
# The per-address rate limit allows RATE_LIMIT_AUTH (10) requests per 15
# minutes; without this an attacker could still drop ten emails into one
# person's inbox every quarter hour. One link a minute is plenty for a person
# whose first email is slow to arrive.
RESEND_COOLDOWN_SECONDS = 60

# At most this many reset emails per account per rolling 24 hours. Past it the
# request still answers the same 200, sends nothing, and is logged.
DAILY_EMAIL_LIMIT = 5


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime) -> datetime:
    """SQLite round-trips DateTime(timezone=True) as naive; treat it as UTC
    (same reasoning as email_verification._as_aware)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def eligible(user: User | None) -> bool:
    """May this account reset its password? See WHO CAN RESET above."""
    return bool(user is not None and user.password_hash and not user.is_suspended)


def find_eligible(db: Session, email: str) -> User | None:
    """The account for `email` if it may reset, else None. `email` must
    already be normalised (lower-cased, stripped) the way signup stores it."""
    user = db.execute(select(User).where(User.email == email)).scalars().first()
    return user if eligible(user) else None


def _outstanding(db: Session, user_id) -> list[PasswordResetToken]:
    return list(db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
    ).scalars().all())


def _lock_account(db: Session, user: User) -> None:
    """Serialise reset work per account: SELECT ... FOR UPDATE on the users
    row (PostgreSQL; a no-op on SQLite, which has one writer anyway). Two
    concurrent requests for the same address then run one after the other,
    and the second sees the first's committed link (cooldown) instead of both
    passing the check and minting two live links."""
    db.execute(select(User.id).where(User.id == user.id).with_for_update())


def issue_token(db: Session, user: User, *, ip: str | None = None,
                now: datetime | None = None) -> str | None:
    """Burn this account's outstanding links and mint a new one. Returns the
    RAW token, or None -- with NOTHING changed, so the link already in the
    person's inbox keeps working -- when:

      * a link was issued less than RESEND_COOLDOWN_SECONDS ago, or
      * DAILY_EMAIL_LIMIT links were already issued in the last 24 hours
        (logged: an inbox is being flooded, or a person is stuck).

    Does not commit; the caller's commit releases the account lock."""
    now = now or _now()
    _lock_account(db, user)
    outstanding = _outstanding(db, user.id)
    for row in outstanding:
        if row.created_at is not None and (
                now - _as_aware(row.created_at)).total_seconds() < RESEND_COOLDOWN_SECONDS:
            return None
    issued_today = db.execute(
        select(func.count(PasswordResetToken.id)).where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.created_at > now - timedelta(hours=24))
    ).scalar_one()
    if issued_today >= DAILY_EMAIL_LIMIT:
        logger.warning("password reset: daily limit (%s per 24h) reached for user %s; "
                       "no email sent", DAILY_EMAIL_LIMIT, user.id)
        return None
    for row in outstanding:
        row.used_at = now  # superseded: stamped, not deleted (audit trail)
    raw = secrets.token_urlsafe(_TOKEN_BYTES)
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash(raw),
        expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
        requested_ip=(ip or "")[:64] or None,
        created_at=now,
    ))
    return raw


def reset_url(raw_token: str) -> str:
    """The frontend reset page, token in the fragment (see module docstring).
    The token is url-safe base64, so it needs no escaping."""
    return f"{settings.frontend_url.rstrip('/')}/reset-password#token={raw_token}"


def _render(email: str, link: str) -> tuple[str, str, str]:
    minutes = settings.password_reset_ttl_minutes
    app = settings.app_name
    subject = f"Reset your {app} password"
    text = (
        f"Someone asked to reset the password for the {app} account {email}.\n\n"
        f"To choose a new password, open this link:\n\n{link}\n\n"
        f"The link works once and expires in {minutes} minutes. Resetting your "
        f"password signs you out on every device and revokes your personal API "
        f"keys; create new keys afterwards if an integration needs one.\n\n"
        f"If you did not ask for this, ignore this email. Your password has not "
        f"changed and nobody can change it without this link.\n"
    )
    html = (
        '<!doctype html><html><body style="font-family:system-ui,-apple-system,'
        'Segoe UI,Roboto,sans-serif;line-height:1.6;color:#111">'
        f'<h2 style="margin:0 0 16px">Reset your {app} password</h2>'
        f"<p>Someone asked to reset the password for the {app} account "
        f"{email}.</p>"
        f'<p style="margin:24px 0"><a href="{link}" '
        'style="background:#1d4ed8;color:#fff;padding:12px 20px;'
        'border-radius:8px;text-decoration:none;display:inline-block">'
        "Choose a new password</a></p>"
        f'<p style="font-size:14px;color:#555">The link works once and expires '
        f"in {minutes} minutes. Resetting your password signs you out on every "
        "device and revokes your personal API keys; create new keys afterwards "
        "if an integration needs one.</p>"
        '<p style="font-size:14px;color:#555">Or paste this into your '
        f'browser:<br><span style="word-break:break-all">{link}</span></p>'
        '<hr style="border:none;border-top:1px solid #eee;margin:24px 0">'
        '<p style="font-size:12px;color:#777">If you did not ask for this, '
        "ignore this email. Your password has not changed and nobody can change "
        "it without this link.</p>"
        "</body></html>"
    )
    return subject, html, text


def send_link(email: str, raw_token: str) -> None:
    """Email an ALREADY-COMMITTED token (the commit-before-send rule from
    email_verification.send_link). Raises EmailSendError on failure."""
    subject, html, text = _render(email, reset_url(raw_token))
    send_email(to=email, subject=subject, html=html, text=text)


def redeem(db: Session, raw_token: str, new_password: str,
           now: datetime | None = None) -> tuple[str, User | None]:
    """Spend a reset link. On RESET the account has its new password hash and
    every outstanding reset link is burnt; the CALLER revokes sessions, writes
    the audit row and commits (one transaction for all of it).

    The password is hashed (600k PBKDF2 rounds) only once the link has proved
    valid, so a flood of made-up tokens costs a hash lookup each, not a
    half-second of CPU each. Raises ValueError if auth.hash_password rejects
    the password (the caller answers 422).

    Every non-RESET outcome leaves the password untouched. An EXPIRED or
    INELIGIBLE link is burnt as well, so it can never be retried."""
    from app.services import auth as auth_svc  # noqa: PLC0415
    now = now or _now()
    if not raw_token:
        return INVALID, None
    row = db.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash(raw_token))
    ).scalars().first()
    if row is None or row.used_at is not None:
        return INVALID, None
    user = db.get(User, row.user_id)
    if user is None:
        return INVALID, None
    # THE CLAIM. A conditional UPDATE, not an attribute write: the read above
    # is not a lock, so two requests with the same link can both get here.
    # Only one UPDATE matches used_at IS NULL (on PostgreSQL the second blocks
    # on the row until the first commits, then matches nothing); the loser is
    # answered INVALID and changes nothing. Whatever happens next, the link is
    # spent: an expired or ineligible link is burnt by this same claim.
    claimed = db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.id == row.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    if claimed != 1:
        return INVALID, None
    row.used_at = now
    if _as_aware(row.expires_at) <= now:
        return EXPIRED, user
    if not eligible(user):
        return INELIGIBLE, user
    new_hash = auth_svc.hash_password(new_password)
    for other in _outstanding(db, user.id):
        other.used_at = now
    user.password_hash = new_hash
    return RESET, user
