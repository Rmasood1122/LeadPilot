"""Cross-channel conversation + stagnation suggestions (Feature A4).

GET  /leads/{lead_id}/conversation          one chronological thread, every channel
GET  /leads/{lead_id}/channel-suggestions
GET  /channel-suggestions                   the account's suggestions (default: open)
POST /channel-suggestions/detect            run the stagnation step for this account now
POST /channel-suggestions/{id}/accept       switch the lead's next scheduled message
POST /channel-suggestions/{id}/dismiss

Owner-scoped (Phase A): a lead or suggestion that is not the caller's is a 404.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import ChannelSuggestion, User
from app.pipeline import channel_orchestrator as orchestrator
from app.services import conversation_thread, crm_service

router = APIRouter(tags=["conversations"])


class ThreadItem(BaseModel):
    """The typed shape of one unified-thread entry (the data model of the
    merged conversation; see app/services/conversation_thread.py)."""
    id: str
    kind: Literal["message", "reply", "call", "booking", "meeting", "channel_suggestion"]
    direction: Literal["outbound", "inbound", "both", "system"]
    channel: str
    at: str | None
    status: str | None = None
    subject: str | None = None
    body: str | None = None
    step_no: int | None = None
    opened: bool | None = None
    open_count: int | None = None
    error: str | None = None
    classification: str | None = None
    authenticity: dict | None = None
    outcome: str | None = None
    duration_seconds: int | None = None
    starts_at: str | None = None
    from_channel: str | None = None
    suggestion_id: str | None = None


class ThreadOut(BaseModel):
    lead_id: str
    items: list[ThreadItem]
    summary: dict


def _owned_suggestion(db: Session, suggestion_id: uuid.UUID, user: User) -> ChannelSuggestion:
    row = db.get(ChannelSuggestion, suggestion_id)
    if row is None:
        raise HTTPException(status_code=404, detail="suggestion not found")
    crm_service.owned_lead(db, row.lead_id, user)   # 404 when not the caller's
    return row


def _raise(exc: orchestrator.SuggestionError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/leads/{lead_id}/conversation", response_model=ThreadOut)
def lead_conversation(lead_id: uuid.UUID, limit: int = Query(default=500, ge=1, le=2000),
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    lead = crm_service.owned_lead(db, lead_id, current_user)
    return conversation_thread.build_thread(db, lead, limit=limit)


@router.get("/leads/{lead_id}/channel-suggestions")
def lead_suggestions(lead_id: uuid.UUID, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> list[dict]:
    lead = crm_service.owned_lead(db, lead_id, current_user)
    rows = db.execute(select(ChannelSuggestion).where(ChannelSuggestion.lead_id == lead.id)
                      .order_by(ChannelSuggestion.created_at.desc())).scalars()
    return [orchestrator.suggestion_out(r) for r in rows]


@router.get("/channel-suggestions")
def account_suggestions(status: str = Query(default="suggested",
                                            pattern="^(suggested|accepted|auto_switched|dismissed|all)$"),
                        limit: int = Query(default=100, ge=1, le=500),
                        db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)) -> list[dict]:
    query = select(ChannelSuggestion).where(ChannelSuggestion.user_id == current_user.id)
    if status != "all":
        query = query.where(ChannelSuggestion.status == status)
    rows = db.execute(query.order_by(ChannelSuggestion.created_at.desc()).limit(limit)).scalars()
    return [orchestrator.suggestion_out(r) for r in rows]


@router.post("/channel-suggestions/detect")
def detect_now(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    return orchestrator.detect_stagnation(db, user_id=current_user.id)


@router.post("/channel-suggestions/{suggestion_id}/accept")
def accept_suggestion(suggestion_id: uuid.UUID, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    row = _owned_suggestion(db, suggestion_id, current_user)
    try:
        return orchestrator.accept(db, row)
    except orchestrator.SuggestionError as exc:
        raise _raise(exc)


@router.post("/channel-suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: uuid.UUID, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)) -> dict:
    row = _owned_suggestion(db, suggestion_id, current_user)
    try:
        orchestrator.dismiss(db, row)
    except orchestrator.SuggestionError as exc:
        raise _raise(exc)
    return orchestrator.suggestion_out(row)
