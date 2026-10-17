"""Persistent sign-in: server-side sessions behind rotating refresh tokens.

WHY STATEFUL. The M5 refresh token was a bare signed JWT: nothing could revoke
it, so "log out" only forgot it on the client, and a copied token stayed valid
for its whole lifetime. A 30-day "stay signed in" makes that unacceptable. Each
refresh token now names an auth_sessions row (its `jti`), which lets logout end
it and lets a replay be recognised.

ROTATION + REUSE DETECTION. Every refresh marks the presented session
`rotated` and issues a new one in the same family. A token is therefore good
for exactly one exchange. If a rotated token turns up again after
AUTH_REFRESH_REUSE_GRACE_SECONDS, two parties hold copies of it -- the whole
family is revoked, signing out both, and the event is written to the security
audit log. Inside the grace window (two tabs refreshing at once) the late
caller gets an access token and no new refresh token: its cookie jar already
holds the winner's.

TRANSPORT. Where the refresh token travels is the API layer's business
(app/api/auth.py): an HttpOnly cookie for the web app, the JSON body for the
native app, the SDK and the CLI. This module only issues, rotates and revokes.

LEGACY TOKENS. Tokens issued before migration 0052 have no jti. While
AUTH_ACCEPT_LEGACY_REFRESH_TOKENS is on, one is exchanged for a tracked session
on first use, so nobody is signed out by the deploy.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.core.rate_limiting import client_ip
from app.db.models import AuthSession, User
from app.services import auth as auth_svc
from app.services import security_audit

logger = logging.getLogger(__name__)

# The header a web client sends to say "my refresh token is in the cookie".
# A cookie is only ever READ when it is present, and a custom header cannot be
# sent cross-origin without a CORS preflight that our allow-list refuses -- so
# a hostile page cannot drive /auth/refresh or /auth/logout with the victim's
# cookie, whatever the SameSite setting.
TRANSPORT_HEADER = "X-Auth-Transport"
COOKIE_TRANSPORT = "cookie"

ROTATED = "rotated"
LOGOUT = "logout"
REUSE_DETECTED = "reuse_detected"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def ttl_seconds(persistent: bool) -> int:
    return (settings.jwt_refresh_ttl_seconds if persistent
            else settings.auth_ephemeral_session_ttl_seconds)


@dataclass
class IssuedTokens:
    user: User
    access_token: str
    refresh_token: str | None      # None = access-only (grace-window refresh)
    persistent: bool

    def bundle(self) -> dict:
        out = {"access_token": self.access_token, "token_type": "bearer",
               "expires_in": settings.jwt_access_ttl_seconds,
               "session_persistent": self.persistent}
        if self.refresh_token is not None:
            out["refresh_token"] = self.refresh_token
            out["refresh_expires_in"] = ttl_seconds(self.persistent)
        return out


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=401, detail=detail)


def _start(db: Session, user: User, *, persistent: bool, request: Request | None,
           family_id: uuid.UUID | None = None, now: datetime) -> AuthSession:
    row = AuthSession(
        id=uuid.uuid4(), user_id=user.id, family_id=family_id or uuid.uuid4(),
        persistent=persistent, expires_at=now + timedelta(seconds=ttl_seconds(persistent)),
        ip=((client_ip(request) or "")[:64] or None) if request is not None else None,
        user_agent=((request.headers.get("user-agent") or "")[:300] or None)
        if request is not None else None,
    )
    db.add(row)
    db.flush()
    return row


def _tokens_for(user: User, row: AuthSession) -> IssuedTokens:
    refresh = auth_svc.issue_refresh_token(
        user.id, session_id=row.id, family_id=row.family_id,
        ttl_seconds=ttl_seconds(row.persistent))
    return IssuedTokens(user=user, access_token=auth_svc.issue_access_token(user.id),
                        refresh_token=refresh, persistent=row.persistent)


def issue_session_tokens(db: Session, user: User, *, persistent: bool = True,
                         request: Request | None = None,
                         now: datetime | None = None) -> IssuedTokens:
    """Sign a user in: a new session family. Commits."""
    row = _start(db, user, persistent=persistent, request=request, now=now or _now())
    tokens = _tokens_for(user, row)
    db.commit()
    return tokens


def revoke_family(db: Session, family_id: uuid.UUID, reason: str,
                  now: datetime | None = None) -> int:
    """Revoke every still-live session in a family. Does not commit."""
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.family_id == family_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now or _now(), revoked_reason=reason)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def revoke_all_for_user(db: Session, user_id: uuid.UUID, reason: str,
                        now: datetime | None = None) -> int:
    """Revoke every still-live session of ONE user. Does not commit."""
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now or _now(), revoked_reason=reason)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


def _live_user(db: Session, user_id) -> User:
    """The account a refresh token may still sign in, or raise.

    An erased account (a GDPR tombstone, app/services/account_erasure.py) is
    answered exactly like a missing one: no new session, no IP or user agent
    recorded for it. A suspended account gets the same 403 the access-token
    chokepoint gives it (app/services/auth.py), instead of fresh tokens.
    """
    from app.services.account_erasure import is_tombstone  # noqa: PLC0415

    user = db.get(User, user_id)
    if user is None or is_tombstone(user):
        raise _unauthorized("user not found")
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="account suspended")
    return user


def _issued_before_password_change(user: User, claims: dict) -> bool:
    """True when this token predates the account's last password change or
    reset (users.password_changed_at), so it must be refused.

    Compared at whole-second resolution because a JWT `iat` is an integer:
    a token minted in the same second as the change counts as after it (a
    sign-in straight after a reset must work). A token with no `iat` cannot
    prove its age and is refused once a change is on record."""
    changed = _aware(getattr(user, "password_changed_at", None))
    if changed is None:
        return False
    iat = claims.get("iat")
    if iat is None:
        return True
    try:
        return int(iat) < int(changed.timestamp())
    except (TypeError, ValueError):
        return True


def rotate(db: Session, refresh_token: str, *, request: Request | None = None,
           now: datetime | None = None) -> IssuedTokens:
    """Exchange a refresh token for new tokens, or raise 401. Commits."""
    now = now or _now()
    payload = auth_svc.decode_token_payload(refresh_token, "refresh")
    user_id = uuid.UUID(payload["sub"])
    jti = payload.get("jti")

    if jti is None:
        if not settings.auth_accept_legacy_refresh_tokens:
            raise _unauthorized("session expired")
        user = _live_user(db, user_id)
        if _issued_before_password_change(user, payload):
            raise _unauthorized("session expired")
        logger.info("auth: exchanging a pre-session refresh token for user %s", user_id)
        return issue_session_tokens(db, user, persistent=True, request=request, now=now)

    try:
        session_id = uuid.UUID(str(jti))
    except ValueError:
        raise _unauthorized("invalid token")
    row = db.get(AuthSession, session_id)
    if row is None or row.user_id != user_id:
        raise _unauthorized("session not found")

    if row.revoked_at is not None:
        rotated_at = _aware(row.rotated_at)
        grace = timedelta(seconds=max(settings.auth_refresh_reuse_grace_seconds, 0))
        if row.revoked_reason == ROTATED and rotated_at is not None and now - rotated_at <= grace:
            user = _live_user(db, row.user_id)
            if _issued_before_password_change(user, payload):
                raise _unauthorized("session revoked")
            return IssuedTokens(user=user, access_token=auth_svc.issue_access_token(user.id),
                                refresh_token=None, persistent=row.persistent)
        if row.revoked_reason == ROTATED:
            revoked = revoke_family(db, row.family_id, REUSE_DETECTED, now)
            security_audit.record(
                db, action=security_audit.AUTH_REFRESH_REUSE, request=request,
                user_id=row.user_id, target_type="auth_session_family",
                target_id=row.family_id, details={"session_id": str(row.id),
                                                  "sessions_revoked": revoked})
            db.commit()
            logger.warning("auth: refresh token reuse for user %s; family %s revoked",
                           row.user_id, row.family_id)
        raise _unauthorized("session revoked")

    if _aware(row.expires_at) <= now:
        raise _unauthorized("session expired")
    user = _live_user(db, row.user_id)
    if _issued_before_password_change(user, payload):
        raise _unauthorized("session revoked")

    # Claim the row atomically. Two concurrent requests with the same token
    # both passed the checks above; only one UPDATE can match revoked_at IS
    # NULL, and the other is answered as a grace-window refresh.
    claimed = db.execute(
        update(AuthSession)
        .where(AuthSession.id == row.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=ROTATED, rotated_at=now, last_used_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    if not claimed:
        db.rollback()
        return IssuedTokens(user=user, access_token=auth_svc.issue_access_token(user.id),
                            refresh_token=None, persistent=row.persistent)

    replacement = _start(db, user, persistent=row.persistent, request=request,
                         family_id=row.family_id, now=now)
    db.execute(update(AuthSession).where(AuthSession.id == row.id)
               .values(replaced_by_id=replacement.id)
               .execution_options(synchronize_session=False))
    tokens = _tokens_for(user, replacement)
    db.commit()
    return tokens


def revoke(db: Session, refresh_token: str, *, request: Request | None = None,
           now: datetime | None = None) -> bool:
    """Log out: revoke the presented token's whole family. Never raises --
    signing out with an expired or garbage token still succeeds client-side.
    Returns whether a session was found. Commits."""
    now = now or _now()
    try:
        payload = auth_svc.decode_token_payload(refresh_token, "refresh", verify_exp=False)
        session_id = uuid.UUID(str(payload.get("jti")))
    except (HTTPException, ValueError):
        return False
    row = db.execute(select(AuthSession).where(AuthSession.id == session_id)).scalar_one_or_none()
    if row is None:
        return False
    revoke_family(db, row.family_id, LOGOUT, now)
    security_audit.record(db, action=security_audit.AUTH_LOGOUT, request=request,
                          user_id=row.user_id, target_type="auth_session_family",
                          target_id=row.family_id)
    db.commit()
    return True


# --------------------------------------------------------------------------
# Connector (OAuth) sessions -- Claude / ChatGPT, DECISIONS.md CONN-AS
# --------------------------------------------------------------------------
#
# The same table, family and atomic-claim machinery as web sessions, with
# three differences the OAuth clients require:
#   * the row carries the client id and the granted scope, and a refresh
#     token is only honoured for the client it was issued to;
#   * a refresh token is issued only when offline_access was granted;
#   * NO grace window. A rotated refresh token presented again is
#     `invalid_grant` -- and, as for web sessions, revokes the family -- and
#     the loser of a concurrent double refresh gets `invalid_grant` too
#     (without revoking anything): the client retries with the token the
#     winner received. An access-only answer is not an OAuth response.

CONNECTOR_REVOKED = "connector_revoked"

OFFLINE_ACCESS = "offline_access"


class OAuthGrantError(Exception):
    """An RFC 6749 token-endpoint error. `error` is the wire code."""

    def __init__(self, error: str = "invalid_grant", description: str = ""):
        super().__init__(description or error)
        self.error = error
        self.description = description


@dataclass
class ConnectorTokens:
    user: User
    session: AuthSession
    access_token: str
    refresh_token: str | None
    scope: str

    def response(self) -> dict:
        """The token endpoint's JSON body (RFC 6749 §5.1)."""
        out = {"access_token": self.access_token, "token_type": "Bearer",
               "expires_in": settings.mcp_access_ttl_seconds, "scope": self.scope}
        if self.refresh_token is not None:
            out["refresh_token"] = self.refresh_token
        return out


def _connector_tokens(user: User, row: AuthSession) -> ConnectorTokens:
    scope = row.scope or ""
    access = auth_svc.issue_mcp_access_token(
        user.id, client_id=row.oauth_client_id, scope=scope,
        audience=settings.mcp_resource, session_id=row.id, family_id=row.family_id)
    refresh = None
    if OFFLINE_ACCESS in scope.split():
        refresh = auth_svc.issue_mcp_refresh_token(
            user.id, client_id=row.oauth_client_id, session_id=row.id,
            family_id=row.family_id, ttl_seconds=ttl_seconds(True))
    return ConnectorTokens(user=user, session=row, access_token=access,
                           refresh_token=refresh, scope=scope)


def start_connector_session(db: Session, user: User, *, client_id: str, scope: str,
                            request: Request | None = None,
                            family_id: uuid.UUID | None = None,
                            now: datetime | None = None) -> ConnectorTokens:
    """A new connector session (a new family unless `family_id`). Flushes,
    does not commit: the token endpoint commits it together with the code
    it redeemed."""
    row = _start(db, user, persistent=True, request=request, family_id=family_id,
                 now=now or _now())
    row.oauth_client_id = client_id
    row.scope = scope
    db.flush()
    return _connector_tokens(user, row)


def rotate_connector(db: Session, refresh_token: str, *, client_id: str,
                     request: Request | None = None,
                     now: datetime | None = None) -> ConnectorTokens:
    """Exchange a connector refresh token, or raise OAuthGrantError. Commits."""
    now = now or _now()
    try:
        payload = auth_svc.decode_mcp_refresh_token(refresh_token)
    except auth_svc.TokenRejected:
        raise OAuthGrantError("invalid_grant", "refresh token is invalid or expired") from None
    row = db.get(AuthSession, uuid.UUID(payload["jti"]))
    if row is None or str(row.user_id) != str(payload["sub"]) or row.oauth_client_id is None:
        raise OAuthGrantError("invalid_grant", "refresh token is not recognised")
    if row.oauth_client_id != client_id or payload.get("client_id") != client_id:
        raise OAuthGrantError("invalid_grant", "refresh token was issued to another client")

    if row.revoked_at is not None:
        if row.revoked_reason == ROTATED:
            revoked = revoke_family(db, row.family_id, REUSE_DETECTED, now)
            security_audit.record(
                db, action=security_audit.AUTH_REFRESH_REUSE, request=request,
                user_id=row.user_id, target_type="auth_session_family",
                target_id=row.family_id,
                details={"session_id": str(row.id), "sessions_revoked": revoked,
                         "oauth_client_id": client_id})
            db.commit()
            logger.warning("oauth: refresh token reuse for user %s, client %s; family %s revoked",
                           row.user_id, client_id, row.family_id)
        raise OAuthGrantError("invalid_grant", "refresh token has been used or revoked")
    if _aware(row.expires_at) <= now:
        raise OAuthGrantError("invalid_grant", "refresh token has expired")
    try:
        user = _live_user(db, row.user_id)
    except HTTPException:
        raise OAuthGrantError("invalid_grant", "the account cannot sign in") from None
    if _issued_before_password_change(user, payload) or not _account_usable(user):
        raise OAuthGrantError("invalid_grant", "the account cannot sign in")

    claimed = db.execute(
        update(AuthSession)
        .where(AuthSession.id == row.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=ROTATED, rotated_at=now, last_used_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    if not claimed:
        db.rollback()
        raise OAuthGrantError("invalid_grant", "refresh token has been used")

    tokens = start_connector_session(db, user, client_id=client_id, scope=row.scope or "",
                                     request=request, family_id=row.family_id, now=now)
    db.execute(update(AuthSession).where(AuthSession.id == row.id)
               .values(replaced_by_id=tokens.session.id)
               .execution_options(synchronize_session=False))
    db.commit()
    return tokens


def _account_usable(user: User) -> bool:
    try:
        auth_svc.check_account_usable(user)
    except HTTPException:
        return False
    return True


def revoke_connector_token(db: Session, token: str, *, client_id: str,
                           request: Request | None = None,
                           now: datetime | None = None) -> bool:
    """RFC 7009: end the connector session family a refresh OR access token
    belongs to. Never raises; a token of another client or of no session is
    ignored. Commits. Returns whether a family was revoked."""
    now = now or _now()
    family = None
    user_id = None
    try:
        payload = auth_svc.decode_mcp_refresh_token(token, verify_exp=False)
        row = db.get(AuthSession, uuid.UUID(payload["jti"]))
        if row is not None and row.oauth_client_id == client_id:
            family, user_id = row.family_id, row.user_id
    except auth_svc.TokenRejected:
        try:
            payload = auth_svc.decode_mcp_access_token(token, audience=settings.mcp_resource)
            row = db.get(AuthSession, uuid.UUID(payload["sid"]))
            if row is not None and row.oauth_client_id == client_id:
                family, user_id = row.family_id, row.user_id
        except (auth_svc.TokenRejected, ValueError):
            return False
    if family is None:
        return False
    revoke_family(db, family, CONNECTOR_REVOKED, now)
    security_audit.record(db, action=security_audit.OAUTH_TOKEN_REVOKED, request=request,
                          user_id=user_id, target_type="auth_session_family",
                          target_id=family, details={"oauth_client_id": client_id})
    db.commit()
    return True


def connector_session_live(db: Session, *, session_id, family_id, user_id) -> bool:
    """May a connector access token naming this session still be used?

    Its own row must exist for this user and not be ended for any reason but
    rotation (a rotated row's access token stays good until it expires --
    Claude refreshes ahead of expiry and may still be using it). And no row
    of its family may have been ended by a logout, a reuse detection or a
    disconnect: revoke_family leaves already-rotated rows as they were, so
    the family has to be checked as a whole.
    """
    try:
        sid = uuid.UUID(str(session_id))
        fam = uuid.UUID(str(family_id))
    except ValueError:
        return False
    row = db.get(AuthSession, sid)
    if (row is None or str(row.user_id) != str(user_id) or row.family_id != fam
            or row.oauth_client_id is None):
        return False
    if row.revoked_at is not None and row.revoked_reason != ROTATED:
        return False
    ended = db.execute(
        select(AuthSession.id).where(
            AuthSession.family_id == fam,
            AuthSession.revoked_at.is_not(None),
            AuthSession.revoked_reason != ROTATED,
        ).limit(1)
    ).first()
    return ended is None
