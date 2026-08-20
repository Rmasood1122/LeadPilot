"""Encryption at rest for secrets we must store (OAuth tokens).

DEPRECATED SHIM: this module used to have its own Fernet instance keyed off
TOKEN_ENCRYPTION_KEY, separate from app/core/crypto.py's ENCRYPTION_KEY.
That split meant tokens encrypted through one path could fail to decrypt
through the other, and the /admin/rotate-encryption-key endpoint (which
only touches app.core.crypto) silently skipped tokens written here.

Fixed by delegating everything to app.core.crypto, which is now the single
source of truth (env var: ENCRYPTION_KEY, + ENCRYPTION_KEY_PREVIOUS during
rotation). Existing callers (app/integrations/gmail.py,
app/services/sequence_engine.py, app/services/whatsapp_optin.py) keep
working unchanged — only the implementation moved.

New code should import app.core.crypto directly instead of this module.
"""

from app.core.crypto import (
    decrypt as decrypt_str,
    decrypt_json,
    encrypt as encrypt_str,
    encrypt_json,
)

__all__ = ["encrypt_str", "decrypt_str", "encrypt_json", "decrypt_json"]
