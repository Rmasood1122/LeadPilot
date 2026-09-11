"""
Integration token store.

All OAuth tokens, API keys, and access tokens are stored encrypted at rest
using Fernet encryption (app.core.crypto). This file is the single storage
and retrieval path for all integration credentials.

The M2 adapters stored tokens in plaintext. The M8-C3 migration
(alembic/versions/0009_m8c3_admin_and_hardening.py) adds the
`encrypted_value` column and backfills existing plaintext rows.
After migration, `plaintext_value` is deprecated and ignored on read.

FEATURE-EXPANSION REPAIR -- THIS CLASS HAD NEVER WORKED
It filtered and wrote on a `key` attribute, but the model's column is
`token_kind` (`UniqueConstraint("user_id", "provider", "token_kind")`), so
every call raised on the first query: `filter_by(key=...)` is an
InvalidRequestError and the constructor rejects `key=` outright. It also
compared a timezone-aware `expires_at` against naive `utcnow()`, which raises
TypeError on PostgreSQL, and passed `user_id` as a string into a UUID column,
which the SQLite bind processor rejects. Nothing noticed because nothing called
it -- webhook_tasks.py imported it and never used it. The feature expansion
requires every new integration to store its credentials here, so it is fixed
rather than worked around:

  * `key` (the public argument name, kept for every documented call site)
    maps onto the `token_kind` column;
  * `user_id=None` is the SYSTEM scope -- deployment-wide credentials the
    admin sets (migration 0023 makes the column nullable). NULLs do not
    collide in the unique constraint, so system-scope uniqueness is enforced
    here by update-in-place rather than by the index;
  * all timestamps are timezone-aware UTC.

Usage:
    from app.integrations.token_store import TokenStore

    # Store a token
    TokenStore.set(db, user_id=user.id, provider="gmail", key="refresh_token", value="1//...")

    # Retrieve a token
    refresh_token = TokenStore.get(db, user_id=user.id, provider="gmail", key="refresh_token")

    # A deployment-wide key (admin panel)
    TokenStore.set(db, user_id=None, provider="openai", key="api_key", value="sk-...")
"""
from __future__ import annotations

import datetime
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.core.crypto import encrypt, decrypt
from app.core.logging import get_logger
from app.models.integration_token import IntegrationToken

logger = get_logger("integrations.token_store")


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _aware(value: datetime.datetime | None) -> datetime.datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)


def _uid(user_id) -> uuid.UUID | None:
    if user_id is None:
        return None
    return user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))


class TokenStore:
    """Static helper class for encrypted integration token storage."""

    @staticmethod
    def _query(db: Session, user_id, provider: str, key: str | None = None):
        uid = _uid(user_id)
        query = db.query(IntegrationToken).filter(IntegrationToken.provider == provider)
        query = (query.filter(IntegrationToken.user_id.is_(None)) if uid is None
                 else query.filter(IntegrationToken.user_id == uid))
        if key:
            query = query.filter(IntegrationToken.token_kind == key)
        return query

    @staticmethod
    def set(
        db: Session,
        user_id: str | uuid.UUID | None,
        provider: str,
        key: str,
        value: str,
        expires_at: datetime.datetime | None = None,
        commit: bool = True,
    ) -> None:
        """
        Encrypt and store (or update) an integration token.

        provider: e.g. "gmail", "whatsapp", "apollo", "hunter", "calendly"
        key:      e.g. "refresh_token", "access_token", "api_key"
        value:    plaintext secret — will be encrypted before storage
        user_id:  None stores a SYSTEM-scope (deployment-wide) credential
        """
        encrypted = encrypt(value)
        existing = TokenStore._query(db, user_id, provider, key).first()

        if existing:
            existing.encrypted_value = encrypted
            existing.value = None
            existing.expires_at = expires_at
            existing.updated_at = _utcnow()
        else:
            db.add(IntegrationToken(
                user_id=_uid(user_id),
                provider=provider,
                token_kind=key,
                encrypted_value=encrypted,
                expires_at=expires_at,
            ))

        if commit:
            db.commit()
        else:
            db.flush()
        logger.info(
            "token_store.set",
            provider=provider,
            key=key,
            user_id=str(user_id) if user_id is not None else "system",
            has_expiry=expires_at is not None,
        )

    @staticmethod
    def get(
        db: Session,
        user_id: str | uuid.UUID | None,
        provider: str,
        key: str,
    ) -> Optional[str]:
        """
        Retrieve and decrypt an integration token.
        Returns None if not found or if the token has expired.
        """
        row = TokenStore._query(db, user_id, provider, key).first()

        if row is None or not row.encrypted_value:
            return None

        expires_at = _aware(row.expires_at)
        if expires_at and expires_at < _utcnow():
            logger.warning(
                "token_store.token_expired",
                provider=provider,
                key=key,
                user_id=str(user_id) if user_id is not None else "system",
                expired_at=expires_at.isoformat(),
            )
            return None

        try:
            return decrypt(row.encrypted_value)
        except Exception as e:
            logger.error(
                "token_store.decrypt_failed",
                provider=provider,
                key=key,
                user_id=str(user_id) if user_id is not None else "system",
                error=str(e),
            )
            return None

    @staticmethod
    def keys(db: Session, user_id, provider: str) -> list[str]:
        """Which keys are stored for user+provider. Never returns values."""
        return [row.token_kind for row in TokenStore._query(db, user_id, provider)
                if row.encrypted_value]

    @staticmethod
    def delete(
        db: Session,
        user_id: str | uuid.UUID | None,
        provider: str,
        key: str | None = None,
    ) -> int:
        """
        Delete token(s) for a user+provider. If key is None, deletes all tokens for that provider.
        Returns count of deleted rows.
        """
        count = TokenStore._query(db, user_id, provider, key).delete(
            synchronize_session=False
        )
        db.commit()
        logger.info(
            "token_store.deleted",
            provider=provider,
            key=key,
            user_id=str(user_id) if user_id is not None else "system",
            count=count,
        )
        return count

    @staticmethod
    def is_valid(
        db: Session,
        user_id: str | uuid.UUID | None,
        provider: str,
        key: str,
    ) -> bool:
        """Return True if a non-expired token exists."""
        return TokenStore.get(db, user_id=user_id, provider=provider, key=key) is not None
