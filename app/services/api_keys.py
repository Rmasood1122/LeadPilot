"""Personal API keys (Feature Group 4 -- what Zapier and Make authenticate with).

Format: "lpk_" + 43 url-safe characters. Only the SHA-256 is stored; the key
is shown once. A key acts as its user for the normal API, EXCEPT the admin
routes: deps.require_admin refuses API-key authentication, so a leaked key
from an admin account cannot reach the admin panel.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ApiKey, User

PREFIX = "lpk_"
MAX_ACTIVE = 10
_TOUCH_EVERY = timedelta(minutes=1)


class ApiKeyLimit(ValueError):
    pass


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create(db: Session, user_id, name: str) -> tuple[ApiKey, str]:
    active = db.execute(select(func.count(ApiKey.id)).where(
        ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))).scalar_one()
    if active >= MAX_ACTIVE:
        raise ApiKeyLimit(f"at most {MAX_ACTIVE} active API keys; revoke one first")
    plaintext = PREFIX + secrets.token_urlsafe(32)
    row = ApiKey(user_id=user_id, name=(name or "API key").strip()[:100] or "API key",
                 prefix=plaintext[:12], key_hash=_hash(plaintext))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, plaintext


def authenticate(db: Session, token: str) -> User | None:
    if not token or not token.startswith(PREFIX):
        return None
    row = db.execute(select(ApiKey).where(ApiKey.key_hash == _hash(token))).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    now = datetime.now(timezone.utc)
    last = row.last_used_at
    if last is not None and last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if last is None or now - last > _TOUCH_EVERY:
        row.last_used_at = now
        db.commit()
    return db.get(User, row.user_id)


def revoke(db: Session, user_id, key_id) -> bool:
    row = db.get(ApiKey, key_id if isinstance(key_id, uuid.UUID) else uuid.UUID(str(key_id)))
    if row is None or row.user_id != user_id:
        return False
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return True


def out(row: ApiKey) -> dict:
    return {
        "id": str(row.id), "name": row.name, "prefix": row.prefix,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked": row.revoked_at is not None,
    }
