"""AI customer support chat + ticket fallback (Feature 3).

GET    /support/faq                 the curated knowledge base (suggested questions)
POST   /support/chat                ask a question, get a grounded answer
GET    /support/chat/sessions       this user's conversations
GET    /support/chat/sessions/{id}  one conversation with its messages
POST   /support/chat/sessions       start a fresh conversation
DELETE /support/chat/sessions/{id}  delete a conversation
POST   /support/tickets             escalate to a human
GET    /support/tickets             this user's tickets

Everything is user-scoped through get_current_user, so one user can never read
another's conversation — there is no route here that takes a user id at all.
Admins read tickets through /admin/support/tickets, which is a separate
surface with its own gate.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.core.rate_limiting import client_ip, enforce_rate_limit
from app.db.base import get_db
from app.db.models import ChatMessage, ChatSession, SupportTicket, User
from app.services import support_chat, support_kb

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])

# One day. The limit itself is RATE_LIMIT_SUPPORT_CHAT on app.core.config.
CHAT_WINDOW_SECONDS = 86_400

# Longest question accepted. Not a UX preference: every character is billed as
# input against the account's Anthropic key on this and every subsequent turn
# of the conversation, since history is replayed.
MAX_QUESTION_CHARS = 2_000


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    # Omit to continue the most recent session, or start the first one.
    session_id: uuid.UUID | None = None


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    body: str = Field(min_length=10, max_length=5_000)
    chat_session_id: uuid.UUID | None = None


class ResolveIn(BaseModel):
    note: str = Field(default="", max_length=2_000)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    """Always emit a UTC-aware ISO string.

    SQLite reads a DateTime(timezone=True) back as NAIVE while PostgreSQL
    returns it aware, so without this the same endpoint emits two different
    formats depending on which database is underneath. Same fix as
    app/api/tutorials.py.
    """
    if value is None:
        return None
    aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return aware.isoformat()


def _require_enabled() -> None:
    """The kill switch. 503, not 500 — this is a deliberate, temporary state."""
    if not settings.support_chat_enabled:
        raise HTTPException(
            status_code=503,
            detail="Support chat is temporarily unavailable. "
                   "You can still submit a ticket.",
        )


def _message_out(message: ChatMessage) -> dict:
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "reason": message.reason,
        "confidence": message.confidence,
        "faq_ids": message.faq_ids or [],
        "suggest_ticket": message.suggest_ticket,
        "created_at": _iso(message.created_at),
    }


def _session_out(session: ChatSession, messages: list[ChatMessage] | None = None) -> dict:
    out = {
        "id": str(session.id),
        "title": session.title,
        "created_at": _iso(session.created_at),
        "last_message_at": _iso(session.last_message_at),
    }
    if messages is not None:
        out["messages"] = [_message_out(m) for m in messages]
    return out


def _ticket_out(ticket: SupportTicket) -> dict:
    return {
        "id": str(ticket.id),
        "subject": ticket.subject,
        "body": ticket.body,
        "status": ticket.status,
        "chat_session_id": str(ticket.chat_session_id) if ticket.chat_session_id else None,
        "created_at": _iso(ticket.created_at),
        "resolved_at": _iso(ticket.resolved_at),
        "resolution_note": ticket.resolution_note,
    }


def _owned_session(db: Session, user: User, session_id: uuid.UUID) -> ChatSession:
    """Fetch a session, or 404.

    The ownership check is part of the WHERE clause, not a separate `if`, so
    another user's session is indistinguishable from one that does not exist —
    no 403-versus-404 oracle for enumerating other people's conversations.
    """
    session = db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user.id,
        )
    ).scalars().first()
    if session is None:
        raise HTTPException(status_code=404, detail="chat session not found")
    return session


def _load_messages(db: Session, session: ChatSession) -> list[ChatMessage]:
    return list(db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.seq, ChatMessage.created_at)
    ).scalars().all())


def _derive_title(text: str) -> str:
    """First line of the opening question, trimmed, as the session label."""
    first = (text or "").strip().splitlines()[0] if text.strip() else "New chat"
    return (first[:77] + "…") if len(first) > 78 else first


# --------------------------------------------------------------------------
# Knowledge base
# --------------------------------------------------------------------------


@router.get("/faq")
def get_faq(user: User = Depends(get_current_user)) -> dict:
    """The curated knowledge base.

    Exposed so the widget can offer real starter questions instead of an empty
    box. It is also the honest answer to "what can this thing actually help
    with?" — the same list the model is restricted to.
    """
    return {
        "faq": [entry.as_dict() for entry in support_kb.FAQ],
        "chat_enabled": settings.support_chat_enabled,
    }


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------


@router.post("/chat")
def chat(request: Request, body: ChatIn, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)) -> dict:
    """Ask the support assistant one question.

    Rate limited PER USER PER DAY (`RATE_LIMIT_SUPPORT_CHAT`), because every
    message spends the account's Anthropic key — this is a cost ceiling first
    and an abuse control second. Keyed on the user id, not the IP: colleagues
    behind one office NAT must not share a budget.

    The limiter runs AFTER FastAPI has validated the body, so an over-long or
    empty message costs no quota — the same ordering guarantee the auth routes
    rely on.

    Both turns are persisted, including refusals and fallbacks, so a confusing
    answer can be explained afterwards without reproducing it.
    """
    _require_enabled()
    enforce_rate_limit(str(user.id), "support_chat",
                       "RATE_LIMIT_SUPPORT_CHAT", CHAT_WINDOW_SECONDS)

    question = body.message.strip()
    if not question:
        raise HTTPException(status_code=422, detail="message cannot be blank")

    if body.session_id is not None:
        session = _owned_session(db, user, body.session_id)
    else:
        session = db.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user.id)
            .order_by(ChatSession.last_message_at.desc().nullslast(),
                      ChatSession.created_at.desc())
        ).scalars().first()
        if session is None:
            session = ChatSession(user_id=user.id, title=_derive_title(question))
            db.add(session)
            db.flush()

    history = [
        {"role": m.role, "content": m.content}
        for m in _load_messages(db, session)
    ]

    # seq continues from the history already loaded, so both turns of this
    # exchange are ordered deterministically regardless of clock resolution.
    next_seq = len(history)
    now = _now()
    db.add(ChatMessage(session_id=session.id, role="user", content=question,
                       seq=next_seq, created_at=now))

    # answer_question NEVER raises — every failure path returns a ticket
    # suggestion rather than propagating, so a model outage degrades the reply
    # instead of 500-ing the request.
    answer = support_chat.answer_question(question, history=history)

    assistant = ChatMessage(
        session_id=session.id,
        seq=next_seq + 1,
        role="assistant",
        content=answer.text,
        reason=answer.reason,
        confidence=answer.confidence,
        faq_ids=list(answer.faq_ids),
        suggest_ticket=answer.suggest_ticket,
        created_at=_now(),
    )
    db.add(assistant)

    session.last_message_at = _now()
    if not session.title:
        session.title = _derive_title(question)
    db.commit()

    return {
        "session_id": str(session.id),
        "answer": answer.as_dict(),
        "message": _message_out(assistant),
    }


@router.get("/chat/sessions")
def list_sessions(limit: int = Query(default=20, ge=1, le=100),
                  db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    sessions = db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.last_message_at.desc().nullslast(),
                  ChatSession.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return {
        "sessions": [_session_out(s) for s in sessions],
        "retention_days": settings.support_chat_retention_days,
    }


@router.get("/chat/sessions/{session_id}")
def get_session(session_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    session = _owned_session(db, user, session_id)
    return _session_out(session, _load_messages(db, session))


@router.post("/chat/sessions", status_code=201)
def new_session(db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    """Start a fresh conversation, so "new chat" does not mean "delete history"."""
    session = ChatSession(user_id=user.id)
    db.add(session)
    db.commit()
    return _session_out(session, [])


@router.delete("/chat/sessions/{session_id}")
def delete_session(session_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    """Delete one conversation and its messages.

    Any ticket raised from it SURVIVES — the FK is ON DELETE SET NULL, so the
    ticket keeps existing with a null session reference rather than vanishing
    because the user tidied up their chat list.
    """
    session = _owned_session(db, user, session_id)
    db.delete(session)
    db.commit()
    return {"deleted": str(session_id)}


# --------------------------------------------------------------------------
# Tickets
# --------------------------------------------------------------------------


@router.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    """Escalate to a human.

    Stored in the database and NOT emailed — email delivery is deferred with
    the rest of the transport work. Storage is the durable half regardless:
    a ticket that is only emailed is a ticket lost whenever the relay is down.

    Deliberately NOT rate limited by the chat budget. Someone who has exhausted
    their daily messages is exactly the person who most needs to reach a human,
    and blocking that would turn a cost control into a support blackout.
    """
    session_id = None
    if body.chat_session_id is not None:
        session_id = _owned_session(db, user, body.chat_session_id).id

    ticket = SupportTicket(
        user_id=user.id,
        chat_session_id=session_id,
        subject=body.subject.strip(),
        body=body.body.strip(),
        status="open",
    )
    db.add(ticket)
    db.commit()
    logger.info("support ticket %s opened by user %s", ticket.id, user.id)
    return _ticket_out(ticket)


@router.get("/tickets")
def list_tickets(db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    tickets = db.execute(
        select(SupportTicket)
        .where(SupportTicket.user_id == user.id)
        .order_by(SupportTicket.created_at.desc())
    ).scalars().all()
    return {"tickets": [_ticket_out(t) for t in tickets]}
