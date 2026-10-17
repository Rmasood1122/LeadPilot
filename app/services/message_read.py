"""Read-side outreach-message queries for the MCP connector.

There was no account-wide list of scheduled/sent messages anywhere (messages
were only reachable per lead, through conversation_thread.build_thread). The
connector needs one, so it lives here, in the service layer, beside the
ownership rule it depends on (DECISIONS.md CONN-SERVICES).

Tenant scoping: a message belongs to whoever owns its lead's strategy's
product -- the same Lead -> Strategy -> Product chain as
crm_service.owned_leads_select. Someone else's message answers 404, never
403, so its existence cannot be inferred.

Message subject/body are model output written from prospect data and are
returned as-is; callers that hand them to a model must treat them as
untrusted (app/mcp/untrusted.py).
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ChannelType, Lead, Message, MessageStatus, Product, Strategy, User,
)

MAX_LIMIT = 50


def owned_messages_select(user: User) -> Select:
    """`SELECT messages ...` pre-filtered to this user's leads."""
    return (
        select(Message)
        .join(Lead, Lead.id == Message.lead_id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == user.id)
    )


def owned_message(db: Session, message_id: uuid.UUID, user: User) -> Message:
    """A message owned by `user`, else 404."""
    message = db.execute(
        owned_messages_select(user).where(Message.id == message_id)
    ).scalar_one_or_none()
    if message is None:
        raise HTTPException(status_code=404, detail="message not found")
    return message


def list_owned(db: Session, user: User, *,
               status: MessageStatus | None = None,
               channel: ChannelType | None = None,
               strategy_id: uuid.UUID | None = None,
               lead_id: uuid.UUID | None = None,
               limit: int = 20, offset: int = 0) -> dict:
    """One page of the user's messages, most recent activity first.

    "Most recent" is sent_at, else scheduled_at, else created_at, so a page
    mixes sent and upcoming messages in the order a person would read them.
    Message ids are the tiebreaker, so offset paging never repeats or skips.
    """
    limit = max(1, min(limit, MAX_LIMIT))
    offset = max(0, offset)
    query = owned_messages_select(user)
    if status is not None:
        query = query.where(Message.status == status)
    if channel is not None:
        query = query.where(Message.channel == channel)
    if strategy_id is not None:
        query = query.where(Lead.strategy_id == strategy_id)
    if lead_id is not None:
        query = query.where(Message.lead_id == lead_id)

    total = int(db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one())
    when = func.coalesce(Message.sent_at, Message.scheduled_at, Message.created_at)
    rows = db.execute(
        query.order_by(when.desc(), Message.id).limit(limit).offset(offset)
    ).scalars().all()
    return {"items": rows, "total": total, "limit": limit, "offset": offset,
            "has_more": offset + len(rows) < total}


def message_out(message: Message, *, include_body: bool) -> dict:
    """The structured fields of a message. `subject`/`body` only on request:
    a list does not need them and they are the untrusted part."""
    out = {
        "id": str(message.id),
        "lead_id": str(message.lead_id),
        "sequence_id": str(message.sequence_id),
        "channel": message.channel.value,
        "step_no": message.step_no,
        "variant": message.variant,
        "status": message.status.value,
        "scheduled_at": message.scheduled_at.isoformat() if message.scheduled_at else None,
        "sent_at": message.sent_at.isoformat() if message.sent_at else None,
        "opened_at": message.opened_at.isoformat() if message.opened_at else None,
        "open_count": message.open_count,
    }
    if include_body:
        out["subject"] = message.subject
        out["body"] = message.body
        out["error"] = message.error
    return out
