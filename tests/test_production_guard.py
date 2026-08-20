"""The production startup guard must block exactly the quiet misconfigurations
and stay out of the way everywhere else.

Each case here maps to a real production failure mode documented in
app/core/production_guard.py — an unset SECRET_KEY producing per-process JWT
keys (intermittent 401s), an unset ENCRYPTION_KEY that only surfaces on first
OAuth token access, and an unset CORS_ORIGINS that silently leaves the API
allowing localhost only.
"""

import pytest
from cryptography.fernet import Fernet

from app.core.production_guard import (
    ProductionConfigError,
    is_production,
    validate_production_config,
)

_GOOD_SECRET = "s" * 48
_GOOD_FERNET = Fernet.generate_key().decode()
_GOOD_CORS = "https://app.example.com"
_GOOD_BASE_URL = "https://api.example.com"
_GOOD_SENDER = "Example Ltd, 42 Real Street, Manchester, M1 2AB, UK"


# Any non-loopback redis URL. The guard only rejects unset/loopback values.
_GOOD_REDIS_URL = "rediss://default:token@example.upstash.io:6379"


def _prod_env(monkeypatch, **overrides):
    """A fully valid production environment, with selective overrides.

    A value of None means "unset this variable".
    """
    env = {
        "APP_ENV": "production",
        "SECRET_KEY": _GOOD_SECRET,
        "ENCRYPTION_KEY": _GOOD_FERNET,
        "CORS_ORIGINS": _GOOD_CORS,
        "PUBLIC_BASE_URL": _GOOD_BASE_URL,
        "SENDER_IDENTITY": _GOOD_SENDER,
        "REDIS_URL": _GOOD_REDIS_URL,
    }
    env.update(overrides)
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


class TestNonProductionIsUntouched:
    @pytest.mark.parametrize("env", ["development", "test", "staging", ""])
    def test_no_op_outside_production(self, monkeypatch, env):
        """The guard must never fire in dev/test — the whole suite runs with
        none of these set."""
        monkeypatch.setenv("APP_ENV", env)
        for key in ("SECRET_KEY", "ENCRYPTION_KEY", "CORS_ORIGINS",
                    "PUBLIC_BASE_URL", "SENDER_IDENTITY", "REDIS_URL"):
            monkeypatch.delenv(key, raising=False)
        validate_production_config()  # must not raise

    @pytest.mark.parametrize("env,expected", [
        ("production", True), ("prod", True), ("live", True),
        ("PRODUCTION", True), ("development", False), ("test", False),
    ])
    def test_is_production_recognises_env(self, env, expected):
        assert is_production(env) is expected


class TestValidProductionPasses:
    def test_fully_configured_production_starts(self, monkeypatch):
        _prod_env(monkeypatch)
        validate_production_config()  # must not raise


class TestSecretKey:
    def test_unset_secret_key_blocks_startup(self, monkeypatch):
        _prod_env(monkeypatch, SECRET_KEY=None)
        with pytest.raises(ProductionConfigError, match="SECRET_KEY is not set"):
            validate_production_config()

    def test_placeholder_secret_key_blocks_startup(self, monkeypatch):
        _prod_env(monkeypatch, SECRET_KEY="change-me-in-production-" + "x" * 20)
        with pytest.raises(ProductionConfigError, match="placeholder"):
            validate_production_config()

    def test_short_secret_key_blocks_startup(self, monkeypatch):
        _prod_env(monkeypatch, SECRET_KEY="tooshort")
        with pytest.raises(ProductionConfigError, match="at least"):
            validate_production_config()


class TestEncryptionKey:
    def test_unset_encryption_key_blocks_startup(self, monkeypatch):
        _prod_env(monkeypatch, ENCRYPTION_KEY=None)
        with pytest.raises(ProductionConfigError, match="ENCRYPTION_KEY is not set"):
            validate_production_config()

    def test_malformed_encryption_key_blocks_startup(self, monkeypatch):
        """A non-Fernet key must be caught at boot, not on first token access."""
        _prod_env(monkeypatch, ENCRYPTION_KEY="not-a-valid-fernet-key")
        with pytest.raises(ProductionConfigError, match="not a valid Fernet key"):
            validate_production_config()


class TestCorsOrigins:
    def test_unset_cors_blocks_startup(self, monkeypatch):
        _prod_env(monkeypatch, CORS_ORIGINS=None)
        with pytest.raises(ProductionConfigError, match="CORS_ORIGINS is not set"):
            validate_production_config()

    @pytest.mark.parametrize("origins", [
        "http://localhost:3000",
        "https://app.example.com,http://localhost:3000",
        "http://127.0.0.1:3000",
    ])
    def test_localhost_origin_blocks_startup(self, monkeypatch, origins):
        _prod_env(monkeypatch, CORS_ORIGINS=origins)
        with pytest.raises(ProductionConfigError, match="local development origin"):
            validate_production_config()

    def test_plaintext_http_origin_blocks_startup(self, monkeypatch):
        _prod_env(monkeypatch, CORS_ORIGINS="http://app.example.com")
        with pytest.raises(ProductionConfigError, match="plaintext http"):
            validate_production_config()

    @pytest.mark.parametrize("origins", [
        '["https://app.example.com","https://www.app.example.com"]',
        '["https://app.example.com"]',
        "'https://app.example.com'",
    ])
    def test_json_array_format_blocks_startup(self, monkeypatch, origins):
        """.env.production.example documented a JSON array, but app/main.py
        splits on commas — so the origins never match and every browser request
        is CORS-blocked while the API itself looks perfectly healthy."""
        _prod_env(monkeypatch, CORS_ORIGINS=origins)
        with pytest.raises(ProductionConfigError, match="comma-separated list"):
            validate_production_config()

    def test_valid_multi_origin_csv_passes(self, monkeypatch):
        _prod_env(
            monkeypatch,
            CORS_ORIGINS="https://app.example.com,https://www.app.example.com",
        )
        validate_production_config()  # must not raise


class TestRedisUrl:
    """REDIS_URL must not silently fall back to localhost.

    The failure this guards against is invisible by construction: Celery reads
    CELERY_BROKER_URL, so broker, beat and workers all stay healthy while only
    the beat heartbeat, response cache, circuit breakers and rate limiter
    break. settings.redis_url has a NON-EMPTY localhost default, so nothing
    errors — the app just talks to a Redis that is not there. Observed live on
    the Render worker, 2026-08-20.
    """

    def test_unset_is_rejected(self, monkeypatch):
        _prod_env(monkeypatch, REDIS_URL=None)
        with pytest.raises(ProductionConfigError, match="REDIS_URL is not set"):
            validate_production_config()

    @pytest.mark.parametrize("url", [
        "redis://localhost:6379/0",
        "redis://127.0.0.1:6379/0",
        "rediss://localhost:6379",
    ])
    def test_loopback_is_rejected(self, monkeypatch, url):
        _prod_env(monkeypatch, REDIS_URL=url)
        with pytest.raises(ProductionConfigError, match="loopback"):
            validate_production_config()

    def test_real_remote_url_passes(self, monkeypatch):
        _prod_env(monkeypatch, REDIS_URL="rediss://default:tok@real.upstash.io:6379")
        validate_production_config()  # must not raise


class TestReporting:
    def test_all_problems_reported_together(self, monkeypatch):
        """Fixing one var per redeploy is a slow way to learn about three."""
        _prod_env(monkeypatch, SECRET_KEY=None, ENCRYPTION_KEY=None,
                  CORS_ORIGINS=None)
        with pytest.raises(ProductionConfigError) as exc:
            validate_production_config()
        message = str(exc.value)
        assert "3 unsafe production" in message
        assert "SECRET_KEY" in message
        assert "ENCRYPTION_KEY" in message
        assert "CORS_ORIGINS" in message


class TestPublicBaseUrl:
    """Unsubscribe links are built from this — a localhost value is a CAN-SPAM
    violation shipped in real email, not a cosmetic problem."""

    def test_unset_blocks_startup(self, monkeypatch):
        _prod_env(monkeypatch, PUBLIC_BASE_URL=None)
        with pytest.raises(ProductionConfigError, match="PUBLIC_BASE_URL is not set"):
            validate_production_config()

    @pytest.mark.parametrize("url", [
        "http://localhost:8000",
        "https://127.0.0.1:8000",
    ])
    def test_local_url_blocks_startup(self, monkeypatch, url):
        _prod_env(monkeypatch, PUBLIC_BASE_URL=url)
        with pytest.raises(ProductionConfigError, match="CAN-SPAM"):
            validate_production_config()

    def test_plaintext_http_blocks_startup(self, monkeypatch):
        _prod_env(monkeypatch, PUBLIC_BASE_URL="http://api.example.com")
        with pytest.raises(ProductionConfigError, match="use https"):
            validate_production_config()


class TestSenderIdentity:
    """CAN-SPAM requires a real physical postal address in the footer."""

    def test_unset_blocks_startup(self, monkeypatch):
        _prod_env(monkeypatch, SENDER_IDENTITY=None)
        with pytest.raises(ProductionConfigError, match="SENDER_IDENTITY is not set"):
            validate_production_config()

    @pytest.mark.parametrize("value", [
        "LeadPilot User, 123 Main St, City, Country",
        "Acme, 123 Main St, Springfield",
        "Acme Ltd, City, Country",
    ])
    def test_placeholder_address_blocks_startup(self, monkeypatch, value):
        _prod_env(monkeypatch, SENDER_IDENTITY=value)
        with pytest.raises(ProductionConfigError, match="placeholder address"):
            validate_production_config()

    def test_real_address_passes(self, monkeypatch):
        _prod_env(monkeypatch,
                  SENDER_IDENTITY="Example Ltd, 42 Real Street, Manchester, M1 2AB, UK")
        validate_production_config()
