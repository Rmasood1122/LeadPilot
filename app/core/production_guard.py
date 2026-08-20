"""Refuse to boot a production process that is misconfigured in a way that
fails *quietly* rather than loudly.

Every check here exists because the failure it prevents does NOT look like a
crash — it looks like the app working, until it doesn't:

* **SECRET_KEY unset** — `app/services/auth.py::_secret()` falls back to a
  RANDOM PER-PROCESS secret. One process is fine. Production runs uvicorn with
  `--workers 2` behind three Celery containers, so every process signs with a
  different key: a token minted by worker 1 is rejected by worker 2 and users
  see intermittent, unreproducible 401s. Nothing logs an error.
* **ENCRYPTION_KEY unset** — raises, but only at the FIRST OAuth token
  encrypt/decrypt, which can be days after deploy and far from the cause.
* **CORS_ORIGINS unset** — `app/main.py` defaults it to
  `http://localhost:3000`, so a deployed API silently allows only localhost and
  the real frontend is CORS-blocked in the browser with nothing wrong
  server-side.
* **PUBLIC_BASE_URL unset** — unsubscribe links, WhatsApp opt-in links and
  media URLs are built from it and default to `http://localhost:8000`. Real
  email would ship with an unsubscribe link no recipient can use (CAN-SPAM).
* **SENDER_IDENTITY unset** — the CAN-SPAM footer address defaults to the
  literal placeholder "123 Main St, City, Country".

All problems are collected and reported together — fixing one env var,
redeploying, and discovering the next one is a slow way to learn about three.

Deliberately scoped to production: `app_env` in {production, prod, live}.
Development and test are unaffected, which is why the whole suite still runs
without any of these set.
"""

from __future__ import annotations

import os

_PRODUCTION_ENVS = {"production", "prod", "live"}

# Values that are obviously not real secrets. Substring match, case-insensitive.
_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "dev-secret",
    "test-secret",
    "placeholder",
    "your-secret",
    "insecure",
    "xxxxx",
)

_MIN_SECRET_LENGTH = 32


class ProductionConfigError(RuntimeError):
    """Raised at startup when production configuration is unsafe."""


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _check_secret_key(problems: list[str]) -> None:
    value = os.getenv("SECRET_KEY", "").strip()
    if not value:
        problems.append(
            "SECRET_KEY is not set. Each process would generate its own random "
            "JWT signing key, so tokens issued by one worker are rejected by "
            "the next (intermittent 401s). Generate one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
        return
    if _is_placeholder(value):
        problems.append(
            "SECRET_KEY looks like a placeholder value, not a generated secret."
        )
    elif len(value) < _MIN_SECRET_LENGTH:
        problems.append(
            f"SECRET_KEY is only {len(value)} characters; use at least "
            f"{_MIN_SECRET_LENGTH}."
        )


def _check_encryption_key(problems: list[str]) -> None:
    value = os.getenv("ENCRYPTION_KEY", "").strip()
    if not value:
        problems.append(
            "ENCRYPTION_KEY is not set. Stored OAuth tokens cannot be "
            "encrypted or decrypted, and this surfaces only on the first "
            "Gmail/Calendly/WhatsApp token access. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
        return
    # Validate it is a usable Fernet key now, not on first use.
    try:
        from cryptography.fernet import Fernet

        Fernet(value.encode())
    except Exception as exc:  # noqa: BLE001 - any failure means unusable key
        problems.append(f"ENCRYPTION_KEY is not a valid Fernet key: {exc}")


def _check_cors_origins(problems: list[str]) -> None:
    raw = os.getenv("CORS_ORIGINS", "").strip()
    if not raw:
        problems.append(
            "CORS_ORIGINS is not set. app/main.py would fall back to "
            "'http://localhost:3000', so the deployed frontend is CORS-blocked "
            "in the browser while the API itself looks healthy. Set it to the "
            "real frontend origin(s), comma-separated."
        )
        return
    # app/main.py parses this by splitting on commas. A JSON array — which is
    # what .env.production.example used to document — splits into fragments
    # like '["https://app.example.com"' that can never match a browser Origin
    # header. The API still returns 200 to curl and every healthcheck passes;
    # only the browser sees the failure, as a CORS error with no server-side
    # trace. Verified live: the JSON form yields no access-control-allow-origin
    # header at all, the comma-separated form yields the correct one.
    if any(ch in raw for ch in "[]\"'"):
        problems.append(
            "CORS_ORIGINS must be a plain comma-separated list, not a JSON "
            "array. app/main.py splits this value on commas, so brackets and "
            "quotes become part of the origin string and never match a real "
            "browser Origin — the API looks healthy while every cross-origin "
            "request is blocked. Use: https://app.example.com,https://www.app.example.com"
        )
        return

    origins = [o.strip() for o in raw.split(",") if o.strip()]
    local = [o for o in origins if "localhost" in o or "127.0.0.1" in o]
    if local:
        problems.append(
            f"CORS_ORIGINS contains local development origin(s) {local} in a "
            "production environment. Remove them."
        )
    insecure = [
        o for o in origins
        if o.startswith("http://") and "localhost" not in o and "127.0.0.1" not in o
    ]
    if insecure:
        problems.append(
            f"CORS_ORIGINS uses plaintext http:// for {insecure}; production "
            "origins should be https://."
        )


def _check_public_base_url(problems: list[str]) -> None:
    """PUBLIC_BASE_URL is what unsubscribe links are built from.

    `app/config.py` defaults it to http://localhost:8000 and it was absent from
    .env.production.example entirely, so a production deploy would have sent
    real marketing email whose unsubscribe link
    (app/services/sequence_engine.py) pointed at localhost. That is a CAN-SPAM
    violation — no recipient can act on it — and dead unsubscribe links are a
    fast route to a spam-folder reputation. The same value builds WhatsApp
    opt-in links and media URLs.
    """
    value = os.getenv("PUBLIC_BASE_URL", "").strip()
    if not value:
        problems.append(
            "PUBLIC_BASE_URL is not set. It defaults to http://localhost:8000, "
            "which is what unsubscribe links, WhatsApp opt-in links and media "
            "URLs are built from — every one of them would be unreachable for "
            "recipients. Set it to the public API origin."
        )
        return
    if "localhost" in value or "127.0.0.1" in value:
        problems.append(
            f"PUBLIC_BASE_URL is {value!r}. Unsubscribe links built from it "
            "would be unreachable for recipients (CAN-SPAM)."
        )
    elif value.startswith("http://"):
        problems.append(
            f"PUBLIC_BASE_URL is {value!r}; use https:// for links that appear "
            "in outbound email."
        )


_PLACEHOLDER_SENDER_MARKERS = ("123 main st", "city, country", "your address")


def _check_sender_identity(problems: list[str]) -> None:
    """CAN-SPAM requires a real physical postal address in the footer.

    The default is the literal placeholder
    "LeadPilot User, 123 Main St, City, Country", and it was absent from every
    env template — so it would have shipped verbatim in production email.
    """
    value = os.getenv("SENDER_IDENTITY", "").strip()
    if not value:
        problems.append(
            "SENDER_IDENTITY is not set. It defaults to the placeholder "
            "'LeadPilot User, 123 Main St, City, Country', which would appear "
            "as the CAN-SPAM physical address in every outbound email. Set it "
            "to a real postal address."
        )
        return
    lowered = value.lower()
    if any(marker in lowered for marker in _PLACEHOLDER_SENDER_MARKERS):
        problems.append(
            f"SENDER_IDENTITY still looks like the placeholder address "
            f"({value!r}). CAN-SPAM requires a real physical postal address."
        )


def is_production(app_env: str | None = None) -> bool:
    env = (app_env if app_env is not None else os.getenv("APP_ENV", "")).strip().lower()
    return env in _PRODUCTION_ENVS


def validate_production_config(app_env: str | None = None) -> None:
    """Raise ProductionConfigError listing every misconfiguration.

    No-op outside production. Call this as early in startup as possible — the
    whole point is to fail before the process starts serving traffic.
    """
    if not is_production(app_env):
        return

    problems: list[str] = []
    _check_secret_key(problems)
    _check_encryption_key(problems)
    _check_cors_origins(problems)
    _check_public_base_url(problems)
    _check_sender_identity(problems)

    if problems:
        numbered = "\n".join(f"  {i}. {p}" for i, p in enumerate(problems, 1))
        raise ProductionConfigError(
            f"Refusing to start: {len(problems)} unsafe production "
            f"configuration problem(s) found.\n{numbered}\n"
            "Set these in the deployment environment and redeploy."
        )
