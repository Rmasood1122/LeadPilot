"""Monthly voice (style) interview. Every query is filtered on current_user.id.
Open to every plan: the point is that every user's messages sound like them."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import User, VoiceInterview
from app.services import voice_interview as vi

router = APIRouter(prefix="/interview", tags=["interview"])


class StartIn(BaseModel):
    mode: str = Field(max_length=10)
    voice_notice_ack: bool = False


class AnswerIn(BaseModel):
    index: int = Field(ge=0, le=20)
    text: str = Field(max_length=20000)


class AnswersIn(BaseModel):
    answers: list[AnswerIn] = Field(max_length=len(vi.QUESTIONS))


class ApplyIn(BaseModel):
    profile: dict | None = None


class SnoozeIn(BaseModel):
    days: int


def _out(r: VoiceInterview) -> dict:
    return {"id": str(r.id), "mode": r.mode, "status": r.status,
            "answers": r.answers_json or [], "proposed_profile": r.proposed_profile_json,
            "recommendations": vi.recommendations(r.proposed_profile_json)
            if r.proposed_profile_json else [],
            "next_due_at": r.next_due_at}


def _run(fn, *args):
    try:
        return fn(*args)
    except vi.InterviewError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)


@router.get("/status")
def status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    open_row = vi.open_one(db, current_user)
    return {"due": vi.is_due(db, current_user), "questions": vi.QUESTIONS,
            "open_interview_id": str(open_row.id) if open_row else None,
            "has_style_profile": bool(current_user.style_profile_json)}


@router.post("/start")
def start(body: StartIn, db: Session = Depends(get_db),
          current_user: User = Depends(get_current_user)) -> dict:
    return _out(_run(vi.start, db, current_user, body.mode, body.voice_notice_ack))


@router.post("/snooze")
def snooze(body: SnoozeIn, db: Session = Depends(get_db),
           current_user: User = Depends(get_current_user)) -> dict:
    return _out(_run(vi.snooze, db, current_user, body.days))


@router.delete("")
def erase(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    return {"deleted": vi.erase(db, current_user)}


@router.get("/{interview_id}")
def get_one(interview_id: uuid.UUID, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)) -> dict:
    return _out(_run(vi.get_own, db, current_user, interview_id))


@router.put("/{interview_id}/answers")
def answers(interview_id: uuid.UUID, body: AnswersIn, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)) -> dict:
    return _out(_run(vi.save_answers, db, current_user, interview_id,
                     [a.model_dump() for a in body.answers]))


@router.post("/{interview_id}/finish")
def finish(interview_id: uuid.UUID, db: Session = Depends(get_db),
           current_user: User = Depends(get_current_user)) -> dict:
    _run(vi.get_own, db, current_user, interview_id)          # 404 before spending a slot
    enforce_rate_limit(str(current_user.id), "ai_action", "RATE_LIMIT_AI_ACTION")
    return _out(_run(vi.finish, db, current_user, interview_id))


@router.post("/{interview_id}/apply")
def apply(interview_id: uuid.UUID, body: ApplyIn, db: Session = Depends(get_db),
          current_user: User = Depends(get_current_user)) -> dict:
    return _out(_run(vi.apply, db, current_user, interview_id, body.profile))


@router.post("/{interview_id}/discard")
def discard(interview_id: uuid.UUID, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)) -> dict:
    return _out(_run(vi.discard, db, current_user, interview_id))
