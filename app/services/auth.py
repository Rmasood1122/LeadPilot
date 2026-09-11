"""Auth (M5) — password hashing + JWT access/refresh tokens.

Hashing: PBKDF2-HMAC-SHA256 (stdlib, no extra native deps), 600k
iterations, per-user random salt, constant-time compare.
Tokens: HS256 JWTs via PyJWT. Access tokens are short-lived; refresh
tokens are long-lived and can ONLY be exchanged at /auth/refresh (the
`typ` claim is checked so a refresh token never works as an access token
and vice versa). JWT_SECRET must be set in production; in development a
process-local random secret is generated (tokens won't survive restarts —
that's intentional pressure to set the env var).
"""

import base64
import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import get_db
from app.db.models import User

logger = logging.getLogger(__name__)

_PBKDF2_ITERATIONS = 600_000
_dev_secret: str | None = None


def _secret() -> str:
    global _dev_secret
    if settings.jwt_secret:
        return settings.jwt_secret
    if _dev_secret is None:
        _dev_secret = secrets.token_urlsafe(48)
        logger.warning("JWT_SECRET unset — using a process-local dev secret; "
                       "tokens will not survive restarts")
    return _dev_secret


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt,
                                 _PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _algo, iters, salt_b64, digest_b64 = stored.split("$")
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt,
                                     int(iters))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------


def _issue(user_id: uuid.UUID, typ: str, ttl_seconds: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": str(user_id), "typ": typ, "iat": now,
         "exp": now + timedelta(seconds=ttl_seconds)},
        _secret(), algorithm="HS256",
    )


def issue_tokens(user_id: uuid.UUID) -> dict:
    return {
        "access_token": _issue(user_id, "access",
                               settings.jwt_access_ttl_seconds),
        "refresh_token": _issue(user_id, "refresh",
                                settings.jwt_refresh_ttl_seconds),
        "token_type": "bearer",
        "expires_in": settings.jwt_access_ttl_seconds,
    }


def decode_token(token: str, expected_typ: str) -> uuid.UUID:
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid token")
    if payload.get("typ") != expected_typ:
        raise HTTPException(status_code=401,
                            detail=f"not a {expected_typ} token")
    return uuid.UUID(payload["sub"])


# --------------------------------------------------------------------------
# Dependency
# --------------------------------------------------------------------------


# The exact string every unverified-user rejection carries. The frontend
# matches on it to decide "send this person to the check-your-email screen"
# rather than "log them out", so it is a contract, not a message: changing it
# silently breaks that branch. It lives here, next to the raise, so the two
# cannot drift.
EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the bearer token to a User, or raise.

    THIS IS THE SINGLE EMAIL-VERIFICATION CHOKEPOINT.

    Every authenticated route in the application resolves its user through this
    one function (app/api/deps.py re-exports it rather than reimplementing it,
    and require_admin builds on it). Putting the check here means an unverified
    account is refused everywhere at once, including routes added later that
    nobody remembered to guard. The alternative considered and rejected was
    adding a dependency to each router: ~30 files, ~30 chances to miss one, and
    a miss is a silent hole rather than a visible error.

    It is a 403, not a 401: the credentials ARE valid. A 401 would send
    frontend/src/lib/api/client.ts into its refresh-then-retry path, which would
    succeed at refreshing, retry, get 401 again, and eventually clear the
    session -- logging out a user whose only problem is an unread email.

    REQUIRE_EMAIL_VERIFICATION=false disables the gate without a code change.
    That switch exists because this is the highest-blast-radius line in the
    feature: if verification ever wrongly locks real users out of a running
    production system, the fix must be an environment variable and a restart,
    not a deploy.
    """
    header = request.headers.get("Authorization") or ""
    if not header.startswith("Bearer ") and request.headers.get("X-API-Key"):
        header = f"Bearer {request.headers['X-API-Key']}"
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = header.removeprefix("Bearer ").strip()

    # Feature Group 4: a personal API key (Zapier, Make, scripts) instead of
    # a short-lived access token. It passes through the SAME verification
    # gate below; deps.require_admin refuses it (request.state.auth_via).
    from app.services import api_keys  # noqa: PLC0415

    if token.startswith(api_keys.PREFIX):
        user = api_keys.authenticate(db, token)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid or revoked API key")
        request.state.auth_via = "api_key"
    else:
        user_id = decode_token(token, "access")
        user = db.get(User, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="user not found")
    if settings.require_email_verification and not user.email_verified:
        raise HTTPException(status_code=403, detail=EMAIL_NOT_VERIFIED)
    return _workspace_principal(request, db, user)


def _workspace_principal(request: Request, db: Session, actor: User) -> User:
    """Feature Group 8: WHOSE data this request acts on.

    With an X-Workspace-Id header naming a workspace the actor is a member of,
    the request acts on that workspace owner's records -- every route that
    scopes by user_id keeps working unchanged -- and the member's role is
    enforced here (app/services/rbac.py). `request.state.actor` is always the
    person who signed in; admin checks and audit use it, never the owner.
    Personal routes (/auth, /me, /devices, ...) ignore the header.
    """
    from app.services import rbac, workspaces  # noqa: PLC0415

    request.state.actor = actor
    request.state.workspace_role = "owner"
    header = request.headers.get(workspaces.HEADER)
    if not header or rbac.is_personal(request.url.path):
        return actor
    ctx = workspaces.resolve(db, actor, header)
    request.state.workspace_id = ctx.workspace.id
    request.state.workspace_role = ctx.role
    if ctx.workspace.owner_user_id == actor.id:
        return actor
    rbac.enforce(ctx.role, request.method, request.url.path)
    owner = db.get(User, ctx.workspace.owner_user_id)
    if owner is None or getattr(owner, "is_suspended", False):
        raise HTTPException(status_code=403, detail="this workspace is unavailable")
    return owner
