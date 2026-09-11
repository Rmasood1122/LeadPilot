"""Outbound webhooks API (Feature Group 4; replaces the M8-C5 raw-SQL version).

    POST   /webhooks/outbound/register      subscribe a URL to events -> 201,
                                            returns the signing secret ONCE
    GET    /webhooks/outbound               the account's subscriptions
    DELETE /webhooks/outbound/{id}          unsubscribe -> 204 (Zapier calls
                                            this when a Zap is turned off)
    POST   /webhooks/outbound/{id}/test     queue a sample delivery
    GET    /webhooks/outbound/deliveries    recent deliveries and their status
    GET    /webhooks/outbound/events        events + sample payloads (Zapier's
                                            "perform list" / sample data)

The M8-C5 routes stay, on the same implementation, for existing callers:
    POST /webhooks/targets · GET /webhooks/targets · DELETE /webhooks/targets/{id}

Authentication is the normal bearer token, or a personal API key (Settings ›
API keys) -- Zapier and Make cannot refresh a 15-minute access token.
"""

from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import User, WebhookTarget
from app.services import webhook_delivery as wd

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class RegisterIn(BaseModel):
    url: str = Field(max_length=1000)
    events: list[str] = Field(min_length=1, max_length=20)
    description: Optional[str] = Field(default=None, max_length=500)
    secret: Optional[str] = Field(default=None, min_length=16, max_length=200)
    source: Literal["api", "zapier", "make"] = "api"


def _owned(db: Session, target_id: uuid.UUID, user: User) -> WebhookTarget:
    target = db.get(WebhookTarget, target_id)
    if target is None or target.user_id != user.id:
        raise HTTPException(status_code=404, detail="webhook not found")
    return target


def _register(db: Session, user: User, url: str, events, *, secret=None, description=None,
              source="api") -> tuple[WebhookTarget, str]:
    enforce_rate_limit(str(user.id), "webhook_register", "RATE_LIMIT_AI_ACTION")
    try:
        return wd.create_target(db, user.id, url, events, secret=secret,
                                description=description, source=source)
    except wd.TargetRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/outbound/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)) -> dict:
    target, secret = _register(db, current_user, body.url, body.events, secret=body.secret,
                               description=body.description, source=body.source)
    return {**wd.target_out(target), "secret": secret}


@router.get("/outbound")
def list_targets(db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> list[dict]:
    rows = db.execute(select(WebhookTarget).where(WebhookTarget.user_id == current_user.id)
                      .order_by(WebhookTarget.created_at.desc())).scalars().all()
    return [wd.target_out(t) for t in rows]


@router.get("/outbound/events")
def list_events(current_user: User = Depends(get_current_user)) -> list[dict]:
    return [{"event": name, "description": text, "sample": wd.SAMPLES.get(name, {}),
             "zapier": name in wd.ZAPIER_EVENTS}
            for name, text in wd.EVENT_DESCRIPTIONS.items()]


@router.get("/outbound/deliveries")
def list_deliveries(limit: int = Query(default=50, ge=1, le=200),
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> list[dict]:
    return wd.list_deliveries(db, current_user.id, limit)


@router.post("/outbound/{target_id}/test", status_code=202)
def test_target(target_id: uuid.UUID, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "webhook_test", "RATE_LIMIT_AI_ACTION")
    target = _owned(db, target_id, current_user)
    if not target.active:
        raise HTTPException(status_code=409, detail="this webhook is disabled")
    delivery = wd.send_test(db, target)
    return {"delivery_id": str(delivery.id), "event": delivery.event_type}


@router.delete("/outbound/{target_id}", status_code=204)
def delete_target(target_id: uuid.UUID, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> Response:
    db.delete(_owned(db, target_id, current_user))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# M8-C5 compatibility
# ---------------------------------------------------------------------------


class WebhookTargetCreate(BaseModel):
    url: str = Field(max_length=1000)
    secret: str = Field(min_length=16, max_length=200)
    event_types: list[str] = Field(min_length=1, max_length=20)
    description: Optional[str] = Field(default=None, max_length=500)


@router.post("/targets", status_code=201)
def create_webhook_target(body: WebhookTargetCreate, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)) -> dict:
    target, _ = _register(db, current_user, body.url, body.event_types, secret=body.secret,
                          description=body.description)
    return {"id": str(target.id), "status": "created"}


@router.get("/targets")
def list_webhook_targets(db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)) -> list[dict]:
    return [{**t, "event_types": t["events"]} for t in list_targets(db, current_user)]


@router.delete("/targets/{target_id}")
def delete_webhook_target(target_id: uuid.UUID, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)) -> dict:
    db.delete(_owned(db, target_id, current_user))
    db.commit()
    return {"status": "deleted", "id": str(target_id)}
