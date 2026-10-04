"""F-OPS-05 -- the ENCRYPTION_KEY-unset warning must describe what really happens.

With no ENCRYPTION_KEY, app/core/crypto.py::_get_fernet raises
EncryptionKeyError, so storing or reading an integration token FAILS. There is
no plaintext fallback. The warning used to say tokens "will NOT be encrypted at
rest", which an operator reads as "it works, unencrypted" -- the opposite of the
fail-closed behaviour.
"""

from __future__ import annotations

import warnings

import pytest

from app.core import crypto
from app.core.config import Settings


@pytest.fixture()
def not_testing(monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("APP_ENV", "production")


def _warning_text() -> str:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings.validate_encryption_key("")
    assert caught, "no warning was raised for an empty ENCRYPTION_KEY"
    return " ".join(str(w.message) for w in caught)


def test_the_warning_does_not_claim_plaintext_storage(not_testing):
    text = _warning_text().lower()
    assert "will not be encrypted" not in text
    assert "unencrypted" not in text
    # "no plaintext fallback" is the correct statement; a claim that tokens are
    # STORED in plaintext is not.
    assert "stored in plaintext" not in text


def test_the_warning_says_token_storage_will_fail(not_testing):
    text = _warning_text()
    assert "ENCRYPTION_KEY" in text
    assert "fail" in text.lower()


def test_the_behaviour_the_warning_describes_is_real(monkeypatch):
    """The claim is only worth making if it is true."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    # _get_fernet is lru_cached; a Fernet built by an earlier test would mask
    # the behaviour under test, so clear it before AND after.
    crypto._get_fernet.cache_clear()
    try:
        with pytest.raises(crypto.EncryptionKeyError):
            crypto._get_fernet()
    finally:
        crypto._get_fernet.cache_clear()


def test_a_set_key_raises_no_warning(not_testing):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert Settings.validate_encryption_key("some-key") == "some-key"
    assert not caught
