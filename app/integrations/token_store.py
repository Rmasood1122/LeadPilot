"""
Integration token store.

All OAuth tokens, API keys, and access tokens are stored encrypted at rest
using Fernet encryption (app.core.crypto). This file is the single storage
and retrieval path for all integration credentials.

The M2 adapters stored tokens in plaintext. The M8-C3 migration
(alembic/versions/xxxx_m8c3_admin_and_hardening.py) adds the
`encrypted_value` column and backfills existing plaintext rows.
After migration, `plaintext_value` is deprecated and ignored on read.

Usage:
    from app.integrations.token_store import TokenStore

    # Store a token
    TokenStore.set(db, user_id=user.id, provider="gmail", key="refresh_token", value="1//...")

    # Retrieve a token
    refresh_token = TokenStore.get(db, user_id=user.id, provider="gmail", key="refresh_token")
"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.crypto import encrypt, decrypt
from app.core.logging import get_logger
from app.models.integration_token import IntegrationToken

logger = get_logger("integrations.token_store")


class TokenStore:
    """Static helper class for encrypted integration token storage."""

    @staticmethod
    def set(
        db: Session,
        user_id: str,
        provider: str,
        key: str,
        value: str,
        expires_at: datetime.datetime | None = None,
    ) -> None:
        """
        Encrypt and store (or update) an integration token.

        provider: e.g. "gmail", "whatsapp", "apollo", "hunter", "calendly"
        key:      e.g. "refresh_token", "access_token", "api_key"
        value:    plaintext secret — will be encrypted before storage
        """
        encrypted = encrypt(value)

        existing = (
            db.query(IntegrationToken)
            .filter_by(user_id=str(user_id), provider=provider, key=key)
            .first()
        )

        if existing:
            existing.encrypted_value = encrypted
            existing.expires_at = expires_at
            existing.updated_at = datetime.datetime.utcnow()
        else:
            db.add(IntegrationToken(
                user_id=str(user_id),
                provider=provider,
                key=key,
                encrypted_value=encrypted,
                expires_at=expires_at,
                created_at=datetime.datetime.utcnow(),
                updated_at=datetime.datetime.utcnow(),
            ))

        db.commit()
        logger.info(
            "token_store.set",
            provider=provider,
            key=key,
            user_id=str(user_id),
            has_expiry=expires_at is not None,
        )

    @staticmethod
    def get(
        db: Session,
        user_id: str,
        provider: str,
        key: str,
    ) -> Optional[str]:
        """
        Retrieve and decrypt an integration token.
        Returns None if not found or if the token has expired.
        """
        row = (
            db.query(IntegrationToken)
            .filter_by(user_id=str(user_id), provider=provider, key=key)
            .first()
        )

        if row is None:
            return None

        if row.expires_at and row.expires_at < datetime.datetime.utcnow():
            logger.warning(
                "token_store.token_expired",
                provider=provider,
                key=key,
                user_id=str(user_id),
                expired_at=row.expires_at.isoformat(),
            )
            return None

        try:
            return decrypt(row.encrypted_value)
        except Exception as e:
            logger.error(
                "token_store.decrypt_failed",
                provider=provider,
                key=key,
                user_id=str(user_id),
                error=str(e),
            )
            return None

    @staticmethod
    def delete(
        db: Session,
        user_id: str,
        provider: str,
        key: str | None = None,
    ) -> int:
        """
        Delete token(s) for a user+provider. If key is None, deletes all tokens for that provider.
        Returns count of deleted rows.
        """
        query = db.query(IntegrationToken).filter_by(user_id=str(user_id), provider=provider)
        if key:
            query = query.filter_by(key=key)
        count = query.delete()
        db.commit()
        logger.info(
            "token_store.deleted",
            provider=provider,
            key=key,
            user_id=str(user_id),
            count=count,
        )
        return count

    @staticmethod
    def is_valid(
        db: Session,
        user_id: str,
        provider: str,
        key: str,
    ) -> bool:
        """Return True if a non-expired token exists."""
        return TokenStore.get(db, user_id=user_id, provider=provider, key=key) is not None
