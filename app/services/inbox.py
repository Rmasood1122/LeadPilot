"""The unified cross-channel inbox (Part 1, Feature 6).

THREADED BY PROSPECT, NOT BY CHANNEL. That is the whole feature. A prospect who
answered an email on Tuesday, was messaged on LinkedIn on Wednesday and replied
there on Thursday is ONE conversation. Every tool that files those as three
inboxes makes a person reconstruct the relationship in their head before they
can answer it, and the usual result is a reply that contradicts something said
on another channel two days earlier.

`conversation_thread.build_thread` already merges one prospect's channels into
one timeline. This module is the LIST above it: every prospect with anything
inbound, ordered by who is waiting longest, with enough per-thread summary that
a person can decide where to start without opening anything.

WHAT "NEEDS A REPLY" MEANS HERE
  * the newest inbound message on any channel is unhandled, AND
  * it came from a person (machine mail -- bounces, out-of-office,
    auto-responders -- is filed, never chased).
Handling is explicit (`handled_at`), not inferred from a later outbound,
because the two commonest ways a reply gets dealt with -- answering from Gmail
directly, and deciding it needs no answer -- leave no outbound row at all. An
inbox that lies about what is outstanding stops being opened.

WHAT IS NOT HERE. No new storage for the thread itself: the timeline comes
from the existing tables through build_thread. Only the handled marker is new.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    InboundReply,
    Lead,
    Message,
    MessageStatus,
    Product,
    Strategy,
    User,
)

#: Inbound rows that are not a person talking. They still appear in a thread
#: (a bounce is worth seeing) but they never make a thread "need a reply".
MACHINE_CLASSES = frozenset({"bounce", "out_of_office", "automated_response"})
MACHINE_AUTHENTICITY = frozenset({"bounce", "out_of_office", "auto_responder", "bot"})

PREVIEW_CHARS = 280


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value else None


def is_from_a_person(reply: InboundReply) -> bool:
    if (reply.classification or "") in MACHINE_CLASSES:
        return False
    return (reply.authenticity_kind or "") not in MACHINE_AUTHENTICITY


def reply_at(reply: InboundReply | None) -> datetime | None:
    """None-tolerant: a thread with no HUMAN reply has no latest human reply,
    and that is an ordinary state, not an error."""
    if reply is None:
        return None
    return _aware(reply.received_at or reply.created_at)


# --------------------------------------------------------------------------
# Building the list
# --------------------------------------------------------------------------


def _owned_leads(user_id):
    return (select(Lead.id)
            .join(Strategy, Strategy.id == Lead.strategy_id)
            .join(Product, Product.id == Strategy.product_id)
            .where(Product.user_id == user_id))


def _thread_for(lead: Lead, replies: list[InboundReply],
                last_outbound: datetime | None) -> dict:
    """One row of the inbox. Cheap: no per-thread timeline is built here."""
    human = [r for r in replies if is_from_a_person(r)]
    ordered = sorted(replies, key=lambda r: reply_at(r) or datetime.min.replace(
        tzinfo=timezone.utc))
    latest = ordered[-1] if ordered else None
    latest_human = sorted(human, key=lambda r: reply_at(r) or datetime.min.replace(
        tzinfo=timezone.utc))[-1] if human else None

    unhandled = [r for r in human if r.handled_at is None]
    channels = Counter(r.channel for r in replies)

    return {
        "lead": {
            "id": str(lead.id),
            "full_name": lead.full_name,
            "title": lead.title,
            "company": lead.company,
            "email": lead.email,
            "status": lead.status.value if lead.status else None,
        },
        # Ordered by volume then name, so the channel the prospect actually
        # uses leads -- the one a reply should probably go back on.
        "channels": [{"channel": ch, "inbound": n}
                     for ch, n in sorted(channels.items(), key=lambda kv: (-kv[1], kv[0]))],
        "reply_count": len(replies),
        "human_reply_count": len(human),
        "unhandled_count": len(unhandled),
        "needs_reply": bool(unhandled),
        "last_inbound_at": _iso(reply_at(latest)),
        "last_human_inbound_at": _iso(reply_at(latest_human)),
        "last_outbound_at": _iso(last_outbound),
        "latest": ({
            "reply_id": str(latest.id),
            "channel": latest.channel,
            "from_address": latest.from_address,
            "subject": latest.subject,
            "preview": " ".join((latest.body or "").split())[:PREVIEW_CHARS],
            "from_a_person": is_from_a_person(latest),
            "handled_at": _iso(latest.handled_at),
            "intent": latest.intent_label,
            "intent_confidence": latest.intent_confidence,
            "classification": latest.classification,
        } if latest else None),
    }


def threads(db: Session, user_id, *, filter: str = "needs_reply",
            channel: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    """The inbox.

    `filter`:
      needs_reply  threads whose newest human reply is unhandled (the default,
                   because that is the only list that is a to-do list)
      all          every thread with anything inbound
      handled      threads with nothing outstanding

    ORDER. `needs_reply` is OLDEST first. A person working an inbox
    newest-first leaves the replies that have waited longest at the bottom,
    and those are exactly the ones where a late answer costs the deal. `all`
    and `handled` are newest-first, because those are browsed, not worked.
    """
    lead_ids = _owned_leads(user_id)
    rows = db.execute(
        select(InboundReply, Lead)
        .join(Lead, Lead.id == InboundReply.lead_id)
        .where(InboundReply.lead_id.in_(lead_ids))
    ).all()

    by_lead: dict = {}
    leads: dict = {}
    for reply, lead in rows:
        by_lead.setdefault(lead.id, []).append(reply)
        leads[lead.id] = lead

    if not by_lead:
        return {"total": 0, "limit": limit, "offset": offset, "filter": filter,
                "needs_reply_total": 0, "items": []}

    # One query for the last outbound per lead, rather than one per thread.
    outbound: dict = {}
    for lead_id, sent_at in db.execute(
        select(Message.lead_id, Message.sent_at)
        .where(Message.lead_id.in_(list(by_lead)), Message.status == MessageStatus.SENT)
    ).all():
        when = _aware(sent_at)
        if when and (outbound.get(lead_id) is None or when > outbound[lead_id]):
            outbound[lead_id] = when

    built = [_thread_for(leads[lead_id], replies, outbound.get(lead_id))
             for lead_id, replies in by_lead.items()]
    if channel:
        built = [t for t in built if any(c["channel"] == channel for c in t["channels"])]

    needs_reply_total = sum(1 for t in built if t["needs_reply"])

    if filter == "needs_reply":
        selected = [t for t in built if t["needs_reply"]]
        # Oldest waiting first -- see the docstring.
        selected.sort(key=lambda t: (t["last_human_inbound_at"] or "", t["lead"]["id"]))
    else:
        selected = [t for t in built if not t["needs_reply"]] if filter == "handled" else built
        selected.sort(key=lambda t: (t["last_inbound_at"] or "", t["lead"]["id"]),
                      reverse=True)

    return {
        "total": len(selected),
        "limit": limit,
        "offset": offset,
        "filter": filter,
        "needs_reply_total": needs_reply_total,
        "items": selected[offset:offset + limit],
    }


def thread_detail(db: Session, lead: Lead) -> dict:
    """One prospect's full cross-channel timeline, plus its inbox state.

    Reuses `conversation_thread.build_thread` rather than re-merging the
    channels: the lead page and the inbox must show the same conversation, and
    two implementations of "merge these tables in time order" would eventually
    disagree about one of them.
    """
    from app.services import conversation_thread  # noqa: PLC0415

    replies = db.execute(
        select(InboundReply).where(InboundReply.lead_id == lead.id)).scalars().all()
    last_outbound = db.execute(
        select(Message.sent_at)
        .where(Message.lead_id == lead.id, Message.status == MessageStatus.SENT)
        .order_by(Message.sent_at.desc()).limit(1)).scalar_one_or_none()
    return {
        **conversation_thread.build_thread(db, lead),
        "inbox": _thread_for(lead, list(replies), _aware(last_outbound)),
    }


# --------------------------------------------------------------------------
# Handling
# --------------------------------------------------------------------------


def mark_handled(db: Session, replies: list[InboundReply], *, actor: User | None = None,
                 handled: bool = True, now: datetime | None = None) -> int:
    """Mark replies handled (or put them back). Returns how many changed.

    Reversible on purpose: "done" is a judgement, and a person who clears a
    thread by mistake must be able to put it back rather than hunting for the
    reply in a list that no longer shows it.
    """
    now = now or datetime.now(timezone.utc)
    changed = 0
    for reply in replies:
        if handled and reply.handled_at is None:
            reply.handled_at = now
            reply.handled_by_user_id = actor.id if actor else None
            changed += 1
        elif not handled and reply.handled_at is not None:
            reply.handled_at = None
            reply.handled_by_user_id = None
            changed += 1
    if changed:
        db.commit()
    return changed


def unhandled_for_lead(db: Session, lead: Lead) -> list[InboundReply]:
    """Every human reply on this prospect still waiting for a decision."""
    replies = db.execute(
        select(InboundReply).where(InboundReply.lead_id == lead.id)).scalars().all()
    return [r for r in replies if r.handled_at is None and is_from_a_person(r)]


def unread_count(db: Session, user_id) -> int:
    """The nav badge: how many prospects are waiting on an answer.

    Counts THREADS, not replies -- a prospect who sent three messages is one
    thing to do, and a badge that says 3 makes the inbox look worse than it is.
    """
    rows = db.execute(
        select(InboundReply).where(InboundReply.lead_id.in_(_owned_leads(user_id)))
    ).scalars().all()
    waiting = {r.lead_id for r in rows if r.handled_at is None and is_from_a_person(r)}
    return len(waiting)
