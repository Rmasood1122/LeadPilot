"""Meeting prep script, readiness checklist and roleplay practice (Part 2).

THE SCRIPT AND THE CHECKLIST
  GET   /meeting-prep/{brief_id}/script        the call script (seeded once)
  PUT   /meeting-prep/{brief_id}/script        the seller's edit
  GET   /meeting-prep/{brief_id}/readiness     what is still missing
  POST  /meeting-prep/{brief_id}/practice-required   make practice blocking

ROLEPLAY
  POST  /practice/sessions                     start one (with or without a lead)
  GET   /practice/sessions                     history, with the score trend
  GET   /practice/sessions/{id}                one session with its transcript
  POST  /practice/sessions/{id}/reply          the seller speaks
  POST  /practice/sessions/{id}/finish         end it and get the feedback

`/practice` is a new prefix. The `/meeting-prep/{id}/*` paths sit under
meeting_prep.py's existing `/meeting-prep/{brief_id}` (longer literal paths, so
no collision).

Practice is available WITHOUT a meeting: `lead_id` is optional on start, so the
standalone tool and the pre-meeting step are the same code path rather than two
that can drift.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import Lead, MeetingPrepBrief, RoleplaySession, User
from app.services import crm_service, meeting_practice, meeting_prep, roleplay

router = APIRouter(tags=["practice"])


class ObjectionIn(BaseModel):
    objection: str = Field(default="", max_length=2000)
    response: str = Field(default="", max_length=2000)


class ScriptIn(BaseModel):
    opening: str = Field(default="", max_length=2000)
    discovery: list[str] = Field(default_factory=list, max_length=12)
    objections: list[ObjectionIn] = Field(default_factory=list, max_length=12)
    close: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=4000)


class PracticeRequiredIn(BaseModel):
    required: bool = True


class StartIn(BaseModel):
    #: Optional: practice is available standalone, for any upcoming meeting or
    #: for none at all.
    lead_id: uuid.UUID | None = None
    brief_id: uuid.UUID | None = None
    difficulty: str = Field(default=roleplay.REALISTIC,
                            pattern="^(easy|realistic|hostile)$")


class ReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class FinishIn(BaseModel):
    #: True = "I stopped early", which records the session without scoring it.
    abandoned: bool = False


def _owned_brief(db: Session, brief_id: uuid.UUID, current_user: User) -> MeetingPrepBrief:
    """404 rather than 403 for another account's brief."""
    brief = db.get(MeetingPrepBrief, brief_id)
    if brief is None or brief.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="brief not found")
    return brief


def _owned_session(db: Session, session_id: uuid.UUID,
                   current_user: User) -> RoleplaySession:
    session = db.get(RoleplaySession, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="session not found")
    return session


# ---------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------


@router.get("/meeting-prep/{brief_id}/script")
def get_script(brief_id: uuid.UUID, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    """The call script: opening, discovery questions, objection lines, close.

    Seeded from the brief the first time it is read, and owned by the seller
    from then on -- `edited: false` means nobody has approved this text yet,
    which the UI says out loud."""
    brief = _owned_brief(db, brief_id, current_user)
    meeting_practice.ensure_script(db, brief)
    return meeting_practice.script_out(brief)


@router.put("/meeting-prep/{brief_id}/script")
def put_script(brief_id: uuid.UUID, body: ScriptIn, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    """Save the seller's edit.

    Regenerating the brief never touches this again."""
    enforce_rate_limit(str(current_user.id), "crm_write", "RATE_LIMIT_CRM_WRITE")
    brief = _owned_brief(db, brief_id, current_user)
    meeting_practice.save_script(db, brief, body.model_dump(), actor=current_user)
    return meeting_practice.script_out(brief)


@router.get("/meeting-prep/{brief_id}/readiness")
def get_readiness(brief_id: uuid.UUID, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    """What is still missing before this call.

    Derived every time, never stored: a stored checklist goes stale and then
    lies."""
    brief = _owned_brief(db, brief_id, current_user)
    return meeting_practice.readiness(db, brief, user_id=current_user.id)


@router.post("/meeting-prep/{brief_id}/practice-required")
def set_practice_required(brief_id: uuid.UUID, body: PracticeRequiredIn,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)) -> dict:
    """Make a rehearsal a blocking step for THIS meeting.

    Per meeting rather than per account: the call worth rehearsing is the one
    that matters, and a global rule turns the checklist into noise on the
    other twenty."""
    brief = _owned_brief(db, brief_id, current_user)
    meeting_practice.set_practice_required(db, brief, body.required)
    return meeting_practice.readiness(db, brief, user_id=current_user.id)


# ---------------------------------------------------------------------------
# Roleplay
# ---------------------------------------------------------------------------


@router.post("/practice/sessions", status_code=201)
def start_session(body: StartIn, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    """Start a practice call. The AI plays the prospect; you practise.

    `lead_id` is optional — practice is available standalone, so the pre-meeting
    step and the "let me rehearse something" button are one code path."""
    enforce_rate_limit(str(current_user.id), "roleplay", "RATE_LIMIT_AI_ACTION")
    lead: Lead | None = None
    brief: MeetingPrepBrief | None = None
    if body.lead_id is not None:
        lead = crm_service.owned_lead(db, body.lead_id, current_user)
    if body.brief_id is not None:
        brief = _owned_brief(db, body.brief_id, current_user)
        lead = lead or db.get(Lead, brief.lead_id)
    elif lead is not None:
        brief = meeting_prep.latest_for_lead(db, lead.id)

    session = roleplay.start(db, current_user, lead=lead, brief=brief,
                             difficulty=body.difficulty)
    return roleplay.session_out(db, session)


@router.get("/practice/sessions")
def list_sessions(lead_id: uuid.UUID | None = None,
                  limit: int = Query(default=50, ge=1, le=200),
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    """Past sessions with the score trend.

    The trend is the point of keeping history: one score is an opinion, a line
    is progress."""
    return roleplay.history(db, current_user.id, lead_id=lead_id, limit=limit)


@router.get("/practice/sessions/{session_id}")
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    return roleplay.session_out(db, _owned_session(db, session_id, current_user))


@router.post("/practice/sessions/{session_id}/reply")
def post_reply(session_id: uuid.UUID, body: ReplyIn, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    """Say your next line; the prospect answers.

    A model failure returns `status: "failed"` with your line already saved —
    losing what a person said because the other side failed to answer is the
    one thing a practice tool must not do."""
    enforce_rate_limit(str(current_user.id), "roleplay", "RATE_LIMIT_AI_ACTION")
    session = _owned_session(db, session_id, current_user)
    result = roleplay.reply(db, session, body.message)
    return {**result, "session": roleplay.session_out(db, session)}


@router.post("/practice/sessions/{session_id}/finish")
def finish_session(session_id: uuid.UUID, body: FinishIn,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    """End the call and get the review.

    A session with fewer than two of your own lines is recorded as abandoned
    and NOT scored: scoring a conversation that never happened produces a
    number that means nothing and then pollutes the improvement chart."""
    enforce_rate_limit(str(current_user.id), "roleplay", "RATE_LIMIT_AI_ACTION")
    session = _owned_session(db, session_id, current_user)
    if session.status != roleplay.ACTIVE:
        raise HTTPException(status_code=409,
                            detail=f"this session is already {session.status}")
    roleplay.finish(db, session, abandoned=body.abandoned)
    return roleplay.session_out(db, session)
