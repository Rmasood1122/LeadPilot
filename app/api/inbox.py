"""The unified cross-channel inbox (Part 1, Feature 6).

GET   /inbox                         threads, by prospect, across every channel
GET   /inbox/count                   prospects waiting on an answer (nav badge)
GET   /inbox/{lead_id}               one prospect's whole conversation
POST  /inbox/{lead_id}/handled       clear (or un-clear) the thread
POST  /inbox/replies/{id}/handled    clear (or un-clear) one reply

`/inbox` is a new prefix. It does not collide with `/crm/replies` (Feature A3),
which lists REPLIES with their authenticity — a different question, filed by
reply rather than by person.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import InboundReply, Lead, User
from app.services import crm_service, inbox

router = APIRouter(tags=["inbox"])


class HandledIn(BaseModel):
    #: False puts a thread back. "Done" is a judgement, and clearing one by
    #: mistake must be undoable without hunting for a reply the list no longer
    #: shows.
    handled: bool = True


@router.get("/inbox")
def list_inbox(
    filter: str = Query(default="needs_reply", pattern="^(needs_reply|all|handled)$"),
    channel: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Every prospect with anything inbound, threaded by PERSON not by channel.

    `needs_reply` (the default) is ordered OLDEST first: an inbox worked
    newest-first leaves the replies that have waited longest at the bottom,
    and those are the ones where a late answer costs the deal. `all` and
    `handled` are newest-first, because those are browsed rather than worked.
    """
    return inbox.threads(db, current_user.id, filter=filter, channel=channel,
                         limit=limit, offset=offset)


@router.get("/inbox/count")
def inbox_count(db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    """Counts THREADS, not replies: a prospect who sent three messages is one
    thing to do, and a badge reading 3 makes the inbox look worse than it is."""
    return {"needs_reply": inbox.unread_count(db, current_user.id)}


@router.get("/inbox/{lead_id}")
def get_inbox_thread(lead_id: uuid.UUID, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict:
    """One prospect's whole conversation, every channel, in time order."""
    lead = crm_service.owned_lead(db, lead_id, current_user)
    return inbox.thread_detail(db, lead)


@router.post("/inbox/{lead_id}/handled")
def mark_thread_handled(lead_id: uuid.UUID, body: HandledIn,
                        db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)) -> dict:
    """Clear the whole thread — every human reply on this prospect.

    Marking handled sends NOTHING. It records that a person has dealt with
    the conversation, wherever they dealt with it."""
    lead = crm_service.owned_lead(db, lead_id, current_user)
    if body.handled:
        targets = inbox.unhandled_for_lead(db, lead)
    else:
        targets = [r for r in db.execute(
            select(InboundReply).where(InboundReply.lead_id == lead.id)).scalars()
            if r.handled_at is not None]
    changed = inbox.mark_handled(db, targets, actor=current_user, handled=body.handled)
    return {"lead_id": str(lead.id), "changed": changed,
            **inbox.thread_detail(db, lead)["inbox"]}


@router.post("/inbox/replies/{reply_id}/handled")
def mark_reply_handled(reply_id: uuid.UUID, body: HandledIn,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)) -> dict:
    """Clear ONE reply. A prospect who replies twice has two things to answer,
    and clearing the first must not clear the second."""
    reply = db.get(InboundReply, reply_id)
    if reply is None or reply.lead_id is None:
        raise HTTPException(status_code=404, detail="reply not found")
    crm_service.owned_lead(db, reply.lead_id, current_user)
    changed = inbox.mark_handled(db, [reply], actor=current_user, handled=body.handled)
    return {"reply_id": str(reply.id), "changed": changed,
            "handled_at": reply.handled_at.isoformat() if reply.handled_at else None}
