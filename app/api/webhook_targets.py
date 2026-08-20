"""
Outbound webhook targets API (M8-C5).

NOTE (integration): the inbound WhatsApp and Calendly webhook routes that were
bundled in the original M8-C5 file are NOT registered from here — the canonical
inbound handlers are the M3/M4 routers (app/api/webhooks.py and
app/api/webhooks_whatsapp.py), which carry signature verification AND
ProcessedWebhook idempotency. Registering both would create duplicate routes.

New C5 endpoints:
  POST   /webhooks/targets        — register a new outbound webhook target
  GET    /webhooks/targets        — list user's registered targets
  DELETE /webhooks/targets/{id}   — remove a target
"""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger
from app.services.webhook_delivery import EVENT_TYPES

logger = get_logger("api.webhooks")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---------------------------------------------------------------------------
# Outbound webhook targets (C5)
# ---------------------------------------------------------------------------

class WebhookTargetCreate(BaseModel):
    url: str
    secret: str
    event_types: list[str]
    description: Optional[str] = None


class WebhookTargetResponse(BaseModel):
    id: str
    url: str
    event_types: list[str]
    active: bool
    description: Optional[str]
    created_at: str


@router.post("/targets", status_code=201)
async def create_webhook_target(
    body: WebhookTargetCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Register a new outbound webhook destination."""
    # Validate event_types
    invalid = [e for e in body.event_types if e not in EVENT_TYPES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event_types: {invalid}. Valid: {sorted(EVENT_TYPES)}",
        )

    from app.core.crypto import encrypt
    from sqlalchemy import text
    import uuid, datetime

    target_id = str(uuid.uuid4())
    encrypted_secret = encrypt(body.secret)

    db.execute(text("""
        INSERT INTO webhook_targets
            (id, user_id, url, secret_encrypted, event_types, active, description, created_at, updated_at)
        VALUES
            (:id, :uid, :url, :secret, :events, true, :desc, :now, :now)
    """), {
        "id": target_id,
        "uid": str(current_user.id),
        "url": str(body.url),
        "secret": encrypted_secret,
        "events": body.event_types,
        "desc": body.description,
        "now": datetime.datetime.utcnow(),
    })
    db.commit()
    logger.info("webhooks.target_created", target_id=target_id, user_id=str(current_user.id))
    return {"id": target_id, "status": "created"}


@router.get("/targets")
async def list_webhook_targets(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> list[dict]:
    """List the current user's registered webhook targets."""
    from sqlalchemy import text
    rows = db.execute(text("""
        SELECT id, url, event_types, active, description, created_at
        FROM webhook_targets
        WHERE user_id = :uid
        ORDER BY created_at DESC
    """), {"uid": str(current_user.id)}).mappings().all()
    return [dict(r) for r in rows]


@router.delete("/targets/{target_id}")
async def delete_webhook_target(
    target_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Delete a webhook target. Only the owner can delete."""
    from sqlalchemy import text
    count = db.execute(text("""
        DELETE FROM webhook_targets
        WHERE id = :id AND user_id = :uid
    """), {"id": target_id, "uid": str(current_user.id)}).rowcount
    db.commit()
    if count == 0:
        raise HTTPException(status_code=404, detail="Webhook target not found")
    return {"status": "deleted", "id": target_id}
