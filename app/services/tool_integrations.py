"""CRUD + helpers for tool integration settings (AegisAudit / PostIQ / SIGNALFORGE).

Settings are stored in `tool_integration_settings` (migration 0032).
Secrets (API keys, tokens) are encrypted via app.core.crypto.

Each save_* helper writes all of its keys in ONE commit, so a failure part
way through never leaves a URL saved without its token.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt, encrypt
from app.db.models import ToolIntegrationSettings

logger = logging.getLogger(__name__)

TOOL_NAMES = {"aegisaudit", "postiq", "signalforge"}

# Keys whose values must be stored encrypted
ENCRYPTED_KEYS = {
    "postiq_token",
    "signalforge_operator_key",
}


def _scope(user_id: uuid.UUID | None):
    col = ToolIntegrationSettings.user_id
    return col.is_(None) if user_id is None else col == user_id


def _row(db: Session, tool: str, key: str, user_id: uuid.UUID | None):
    return db.execute(
        select(ToolIntegrationSettings).where(
            ToolIntegrationSettings.tool_name == tool,
            ToolIntegrationSettings.config_key == key,
            _scope(user_id),
        )
    ).scalar_one_or_none()


def _get(db: Session, tool: str, key: str, user_id: uuid.UUID | None = None) -> str | None:
    row = _row(db, tool, key, user_id)
    if row is None:
        return None
    if row.is_encrypted and row.config_value:
        return decrypt(row.config_value)
    return row.config_value


def _set(db: Session, tool: str, key: str, value: str | None,
         user_id: uuid.UUID | None = None) -> None:
    """Stage one key; the caller commits."""
    encrypted = key in ENCRYPTED_KEYS
    stored_value = encrypt(value) if (encrypted and value) else value

    existing = _row(db, tool, key, user_id)
    if existing:
        existing.config_value = stored_value
        existing.is_encrypted = encrypted
    else:
        db.add(ToolIntegrationSettings(
            user_id=user_id,
            tool_name=tool,
            config_key=key,
            config_value=stored_value,
            is_encrypted=encrypted,
        ))


def _save(db: Session, tool: str, values: dict[str, str | None],
          user_id: uuid.UUID | None = None) -> None:
    try:
        for key, value in values.items():
            _set(db, tool, key, value, user_id=user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _delete(db: Session, tool: str, user_id: uuid.UUID | None = None) -> None:
    db.execute(delete(ToolIntegrationSettings).where(
        ToolIntegrationSettings.tool_name == tool, _scope(user_id)))
    db.commit()


# ── AegisAudit ─────────────────────────────────────────────────────────────

def get_aegisaudit_config(db: Session) -> dict:
    host = _get(db, "aegisaudit", "host") or "127.0.0.1"
    port = _get(db, "aegisaudit", "port") or "8787"
    mode = _get(db, "aegisaudit", "default_mode") or "deep"
    enabled = _get(db, "aegisaudit", "enabled") or "false"
    return {
        "host": host,
        "port": port,
        "base_url": f"http://{host}:{port}",
        "default_mode": mode,
        "enabled": enabled.lower() == "true",
    }


def save_aegisaudit_config(
    db: Session,
    *,
    host: str = "127.0.0.1",
    port: str = "8787",
    default_mode: str = "deep",
    enabled: bool = True,
) -> None:
    _save(db, "aegisaudit", {
        "host": host,
        "port": port,
        "default_mode": default_mode,
        "enabled": str(enabled).lower(),
    })


# ── PostIQ (per user) ──────────────────────────────────────────────────────

def get_postiq_config(db: Session, user_id: uuid.UUID) -> dict | None:
    webapp_url = _get(db, "postiq", "webapp_url", user_id=user_id)
    token = _get(db, "postiq", "postiq_token", user_id=user_id)
    if not webapp_url or not token:
        return None
    return {"webapp_url": webapp_url, "token": token}


def save_postiq_config(db: Session, user_id: uuid.UUID, *, webapp_url: str, token: str) -> None:
    _save(db, "postiq", {"webapp_url": webapp_url, "postiq_token": token}, user_id=user_id)


def delete_postiq_config(db: Session, user_id: uuid.UUID) -> None:
    _delete(db, "postiq", user_id=user_id)


# ── SIGNALFORGE ─────────────────────────────────────────────────────────────

def get_signalforge_config(db: Session) -> dict | None:
    base_url = _get(db, "signalforge", "base_url") or "http://127.0.0.1:8000"
    key = _get(db, "signalforge", "signalforge_operator_key")
    if not key:
        return None
    return {"base_url": base_url, "operator_key": key}


def save_signalforge_config(db: Session, *, base_url: str, operator_key: str) -> None:
    _save(db, "signalforge", {"base_url": base_url, "signalforge_operator_key": operator_key})


def delete_signalforge_config(db: Session) -> None:
    _delete(db, "signalforge")
