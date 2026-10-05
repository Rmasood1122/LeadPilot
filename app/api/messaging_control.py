"""Reply kill switch endpoints. Every lead lookup goes through `_owned_lead`
(strategy -> product -> user), so another account's lead is a 404."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.leads import _owned_lead
from app.db.base import get_db
from app.db.models import CrmActivityKind, Lead, Product, Strategy, User
from app.services import crm_events, messaging_pause as mp, security_audit, system_settings

router = APIRouter(prefix="/messaging", tags=["messaging"])


class PauseIn(BaseModel):
    reason: Literal["manual", "spam", "bounce"] = "manual"


def _paused_contacts(db: Session, user: User) -> int:
    return db.execute(
        select(func.count(Lead.id))
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == user.id, Lead.messaging_paused_at.is_not(None))
    ).scalar_one()


def _status(db: Session, user: User) -> dict:
    return {
        "platform_paused": bool(system_settings.get(db, "messaging_global_pause")),
        "account_paused": user.messaging_paused_at is not None,
        "account_paused_reason": user.messaging_paused_reason,
        "paused_contacts": _paused_contacts(db, user),
    }


@router.get("/status")
def status(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _status(db, user)


@router.post("/pause-all")
def pause_all(request: Request, body: PauseIn | None = None, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> dict:
    reason = (body or PauseIn()).reason
    mp.pause_account(db, user, reason=reason)
    security_audit.record(db, action=security_audit.MESSAGING_ACCOUNT_PAUSED, request=request,
                          user_id=user.id, details={"reason": reason})
    db.commit()
    return _status(db, user)


@router.post("/resume-all")
def resume_all(request: Request, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    mp.resume_account(db, user)
    security_audit.record(db, action=security_audit.MESSAGING_ACCOUNT_RESUMED, request=request,
                          user_id=user.id)
    db.commit()
    return _status(db, user)


@router.post("/leads/{lead_id}/pause")
def pause_lead(lead_id: uuid.UUID, request: Request, body: PauseIn | None = None,
               db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    lead = _owned_lead(db, lead_id, user)
    reason = (body or PauseIn()).reason
    mp.pause_contact(db, lead, reason=reason)
    crm_events.record_activity(db, lead.id, CrmActivityKind.FIELD_CHANGED,
                               actor_user_id=user.id, to_value="messaging paused",
                               meta={"field": "messaging_paused", "reason": reason})
    security_audit.record(db, action=security_audit.MESSAGING_CONTACT_PAUSED, request=request,
                          user_id=user.id, target_type="lead", target_id=lead.id,
                          details={"reason": reason})
    db.commit()
    return {"lead_id": str(lead.id), "paused": True, "reason": reason}


@router.post("/leads/{lead_id}/resume")
def resume_lead(lead_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    lead = _owned_lead(db, lead_id, user)
    mp.resume_contact(db, lead)
    crm_events.record_activity(db, lead.id, CrmActivityKind.FIELD_CHANGED,
                               actor_user_id=user.id, from_value="messaging paused",
                               meta={"field": "messaging_paused"})
    security_audit.record(db, action=security_audit.MESSAGING_CONTACT_RESUMED, request=request,
                          user_id=user.id, target_type="lead", target_id=lead.id)
    db.commit()
    return {"lead_id": str(lead.id), "paused": False, "reason": None}
