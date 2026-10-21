"""The environment the AI evals run the app in, outside pytest.

tests/conftest.py gives the offline suite a sealed environment: an in-memory
database, fake provider keys, in-process mail and SMS, and a local Redis URL.
The live runner (evals/ai/live_eval.py) does not run under pytest, so without
this the app's settings would fall back to .env -- which on a real machine
points Redis and Celery at the PRODUCTION instance (see the note in
tests/conftest.py) and holds real provider keys.

apply() hard-assigns the same values conftest uses, never setdefault, so a
real value already in the shell or in .env cannot leak in. It must run before
anything reads app.config.settings. The model key the live runner uses is its
own (EVAL_ANTHROPIC_API_KEY, passed straight to the SDK), never these.

live_eval's preflight replays every case in this environment and refuses to
run when any result differs from the offline gate's, so a drift between this
file and conftest shows up before money is spent, not after.
"""

from __future__ import annotations

import os

# Same values and reasons as tests/conftest.py's module-level block.
_FIXED = {
    "APP_ENV": "test",
    "ANTHROPIC_API_KEY": "test-key-never-used",
    "DATABASE_URL": "sqlite://",
    "REDIS_URL": "redis://localhost:6380/14",
    "CELERY_BROKER_URL": "redis://localhost:6380/14",
    "CELERY_RESULT_BACKEND": "redis://localhost:6380/14",
    "WHATSAPP_ACCESS_TOKEN": "test-wa-token",
    "WHATSAPP_PHONE_NUMBER_ID": "5550001",
    "WHATSAPP_BUSINESS_ACCOUNT_ID": "waba-test",
    "WHATSAPP_APP_SECRET": "test-app-secret",
    "WHATSAPP_VERIFY_TOKEN": "test-verify-token",
    "SECRET_KEY": "test-secret-key-not-for-production",
    "APOLLO_API_KEY": "apollo-test-key",
    "HUNTER_API_KEY": "hunter-test-key",
    "CALENDLY_WEBHOOK_SECRET": "calendly-secret-test",
    "FIREBASE_CREDENTIALS_JSON": "{}",
    "CELERY_ALWAYS_EAGER": "true",
    "CELERY_EAGER_PROPAGATES": "true",
    "EMAIL_PROVIDER": "memory",
    "PUBLIC_BASE_URL": "http://testserver",
    "FRONTEND_URL": "http://frontend.test",
    "GEOLOCATION_PROVIDER": "disabled",
    "VPN_BLOCK_ENABLED": "false",
    "VPN_DETECTION_PROVIDER": "disabled",
    "SMS_PROVIDER": "memory",
}
# Generated per run, as conftest does: a real Fernet key, never a stored one.
_GENERATED = ("ENCRYPTION_KEY", "TOKEN_ENCRYPTION_KEY")


def apply() -> None:
    from cryptography.fernet import Fernet  # noqa: PLC0415

    if "app.config" in __import__("sys").modules:
        raise RuntimeError("sandbox.apply() must run before app.config is imported")
    os.environ.update(_FIXED)
    for name in _GENERATED:
        os.environ[name] = Fernet.generate_key().decode()
