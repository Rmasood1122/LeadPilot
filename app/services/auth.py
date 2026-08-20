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


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("Authorization") or ""
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    user_id = decode_token(header.removeprefix("Bearer ").strip(), "access")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="user not found")
    return user
