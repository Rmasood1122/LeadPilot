"""
Fernet-based encryption for secrets stored at rest in PostgreSQL.

All integration tokens (Gmail OAuth refresh_token, WhatsApp access_token,
Apollo API key, Hunter API key, Calendly token) are encrypted before being
written to the DB and decrypted on read.

Key management:
  - Primary key: ENCRYPTION_KEY env var (base64-url-encoded 32-byte key)
  - Rotation: use ENCRYPTION_KEY_PREVIOUS to decrypt old values while re-encrypting
    with the new key. After rotation, ENCRYPTION_KEY_PREVIOUS can be cleared.

Generating a key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

NEVER commit the generated key to version control.
"""
from __future__ import annotations

import base64
import os
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

from app.core.logging import get_logger

logger = get_logger("core.crypto")


class EncryptionKeyError(Exception):
    """Raised when the encryption key is missing or invalid."""
    pass


@lru_cache(maxsize=1)
def _get_fernet() -> MultiFernet:
    """
    Build a MultiFernet from ENCRYPTION_KEY (primary) and optionally
    ENCRYPTION_KEY_PREVIOUS (for rotation grace period).

    MultiFernet.encrypt() always uses the first key.
    MultiFernet.decrypt() tries all keys in order — so old values encrypted
    with the previous key continue to decrypt during rotation.
    """
    primary_key = os.getenv("ENCRYPTION_KEY", "")
    if not primary_key:
        raise EncryptionKeyError(
            "ENCRYPTION_KEY environment variable is not set. "
            "Run: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    try:
        primary_fernet = Fernet(primary_key.encode() if isinstance(primary_key, str) else primary_key)
    except Exception as e:
        raise EncryptionKeyError(f"ENCRYPTION_KEY is not a valid Fernet key: {e}") from e

    fernets = [primary_fernet]

    previous_key = os.getenv("ENCRYPTION_KEY_PREVIOUS", "")
    if previous_key:
        try:
            previous_fernet = Fernet(
                previous_key.encode() if isinstance(previous_key, str) else previous_key
            )
            fernets.append(previous_fernet)
            logger.info("crypto.previous_key_loaded_for_rotation")
        except Exception as e:
            logger.warning("crypto.previous_key_invalid", error=str(e))

    return MultiFernet(fernets)


def encrypt(plaintext: str) -> str:
    """
    Encrypt a plaintext string and return a base64-encoded ciphertext string.
    Safe to store in a TEXT column.
    """
    if not plaintext:
        return plaintext
    fernet = _get_fernet()
    ciphertext_bytes = fernet.encrypt(plaintext.encode("utf-8"))
    return ciphertext_bytes.decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """
    Decrypt a ciphertext string (output of encrypt()) back to plaintext.
    Raises InvalidToken if the ciphertext is corrupt or the key is wrong.
    """
    if not ciphertext:
        return ciphertext
    fernet = _get_fernet()
    try:
        plaintext_bytes = fernet.decrypt(ciphertext.encode("utf-8"))
        return plaintext_bytes.decode("utf-8")
    except InvalidToken as e:
        logger.error("crypto.decryption_failed", error="InvalidToken — key mismatch or corrupt data")
        raise


def encrypt_json(data: dict) -> str:
    """Encrypt a JSON-serializable dict. Convenience wrapper around encrypt()."""
    import json
    return encrypt(json.dumps(data))


def decrypt_json(ciphertext: str) -> dict:
    """Decrypt a ciphertext produced by encrypt_json() back to a dict."""
    import json
    return json.loads(decrypt(ciphertext))


def rotate_all_secrets(db_session) -> dict[str, int]:
    """
    Re-encrypt all stored integration tokens from the old key to the new key.

    Call via POST /admin/rotate-encryption-key (which handles key swap in env).
    Returns {"rotated": N, "failed": M}.

    Steps:
      1. Set ENCRYPTION_KEY = new_key and ENCRYPTION_KEY_PREVIOUS = old_key in env
      2. Call this function — it decrypts with the old key (via MultiFernet) and
         re-encrypts with the new primary key
      3. Verify all tokens are accessible
      4. Remove ENCRYPTION_KEY_PREVIOUS from env

    See SECURITY.md for the full rotation procedure.
    """
    from app.models.integration_token import IntegrationToken

    _get_fernet.cache_clear()  # force re-read of new key config
    fernet = _get_fernet()

    tokens = db_session.query(IntegrationToken).all()
    rotated = 0
    failed = 0

    for token_row in tokens:
        try:
            if token_row.encrypted_value:
                # Decrypt with current MultiFernet (tries both old and new key)
                plaintext = decrypt(token_row.encrypted_value)
                # Re-encrypt with the new primary key
                token_row.encrypted_value = encrypt(plaintext)
                rotated += 1
        except Exception as e:
            logger.error(
                "crypto.rotation_failed_for_token",
                token_id=str(token_row.id),
                provider=token_row.provider,
                error=str(e),
            )
            failed += 1

    db_session.commit()
    logger.info("crypto.rotation_complete", rotated=rotated, failed=failed)
    return {"rotated": rotated, "failed": failed}
