"""Transparent attribution ledger (Part 1, Feature 8).

THE QUESTION. A meeting got booked. Which message earned it?

Every outbound tool answers this, and almost all of them answer it the same
dishonest way: credit the last thing sent, present it as fact, and let the user
build a strategy on it. That is fine when the prospect literally replied to
that message and a guess when they did not -- and the two are indistinguishable
in the output, so the guess gets believed.

THIS LEDGER RECORDS THE METHOD AND ITS CONFIDENCE, always:

  direct_reply   the prospect's reply is linked to a specific message
                 (InboundReply.message_id). This is not attribution, it is a
                 fact. Confidence 1.0.
  thread_match   their reply carries the same provider thread_ref as one of
                 our messages. Still evidence, one link weaker. 0.85.
  last_touch     no reply is linked, so the most recent message sent BEFORE
                 the outcome gets the credit. This is the industry default and
                 it is a GUESS -- so its confidence decays with the gap: a
                 booking two hours after a send is far more likely to be that
                 send's doing than one three weeks later.
  none           nothing was sent before the outcome. An inbound booking from
                 someone we never messaged has no touch to credit, and saying
                 so is the correct answer.

WHY A SWEEP AND NOT HOOKS. Outcomes are created in a dozen places -- the
Calendly webhook, our own booking page, the reply router, meeting outcomes, the
CRM deal sync. A hook in each is a hook that will be forgotten in the
thirteenth. One idempotent sweep over outcomes that have no ledger entry covers
every path, past and future, and back-fills history for free.
UNIQUE (outcome_kind, outcome_id) is what makes running it forever safe.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    AttributionEntry,
    InboundReply,
    Lead,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    Product,
    Strategy,
)

logger = logging.getLogger(__name__)

DIRECT_REPLY, THREAD_MATCH, LAST_TOUCH, NONE = (
    "direct_reply", "thread_match", "last_touch", "none")
METHODS = (DIRECT_REPLY, THREAD_MATCH, LAST_TOUCH, NONE)

METHOD_LABELS = {
    DIRECT_REPLY: "They replied to this message",
    THREAD_MATCH: "Their reply is in this message's thread",
    LAST_TOUCH: "Last message sent before the outcome",
    NONE: "Nothing was sent before this",
}

MEETING_BOOKED, POSITIVE_REPLY, WON = "meeting_booked", "positive_reply", "won"
OUTCOME_KINDS = (MEETING_BOOKED, POSITIVE_REPLY, WON)

#: The outcome events worth crediting, and what to call each in the ledger.
CREDITED_EVENTS = {
    OutcomeEvent.BOOKED: MEETING_BOOKED,
    OutcomeEvent.WON: WON,
    OutcomeEvent.REPLIED: POSITIVE_REPLY,
}

#: How last-touch confidence decays. Under the first, a send and an outcome are
#: close enough to be the same conversation; past the last, "the last thing we
#: sent" is barely more than a coincidence.
LAST_TOUCH_BANDS = ((24, 0.7), (72, 0.55), (168, 0.4), (720, 0.25))
LAST_TOUCH_FLOOR = 0.1


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def last_touch_confidence(hours: float | None) -> float:
    """A guess that says how much of a guess it is."""
    if hours is None:
        return LAST_TOUCH_FLOOR
    for limit, value in LAST_TOUCH_BANDS:
        if hours <= limit:
            return value
    return LAST_TOUCH_FLOOR


# --------------------------------------------------------------------------
# Finding the touch
# --------------------------------------------------------------------------


def _sent_messages(db: Session, lead_id, before: datetime) -> list[Message]:
    rows = db.execute(
        select(Message)
        .where(Message.lead_id == lead_id, Message.status == MessageStatus.SENT)
    ).scalars().all()
    return sorted(
        [m for m in rows if _aware(m.sent_at) and _aware(m.sent_at) <= before],
        key=lambda m: _aware(m.sent_at))


def _replies_before(db: Session, lead_id, before: datetime) -> list[InboundReply]:
    rows = db.execute(
        select(InboundReply).where(InboundReply.lead_id == lead_id)).scalars().all()
    out = []
    for reply in rows:
        at = _aware(reply.received_at or reply.created_at)
        if at is None or at <= before:
            out.append(reply)
    return sorted(out, key=lambda r: _aware(r.received_at or r.created_at)
                  or datetime.min.replace(tzinfo=timezone.utc))


def credit(db: Session, lead_id, outcome_at: datetime) -> dict:
    """Which touch earned an outcome at `outcome_at`, and on what basis.

    RETURNS {"message", "method", "confidence", "evidence": [...]} where
    `message` may be None (method "none").
    """
    outcome_at = _aware(outcome_at) or _now()
    sent = _sent_messages(db, lead_id, outcome_at)
    replies = _replies_before(db, lead_id, outcome_at)
    evidence: list[str] = []

    # 1. A reply linked to a specific message. Not attribution -- a fact.
    for reply in reversed(replies):
        if reply.message_id:
            message = db.get(Message, reply.message_id)
            if message is not None:
                evidence.append(
                    f"Their {reply.channel} reply is linked to this message "
                    f"(step {message.step_no}).")
                return {"message": message, "method": DIRECT_REPLY,
                        "confidence": 1.0, "evidence": evidence}

    # 2. Same provider thread. One link weaker, still evidence.
    by_thread = {m.thread_ref: m for m in sent if m.thread_ref}
    for reply in reversed(replies):
        if reply.thread_ref and reply.thread_ref in by_thread:
            message = by_thread[reply.thread_ref]
            evidence.append(
                f"Their reply arrived in the same thread as step {message.step_no} "
                f"on {message.channel.value if message.channel else '?'}.")
            return {"message": message, "method": THREAD_MATCH,
                    "confidence": 0.85, "evidence": evidence}

    # 3. Last touch. The industry default, and a guess -- labelled as one.
    if sent:
        message = sent[-1]
        hours = (outcome_at - _aware(message.sent_at)).total_seconds() / 3600
        evidence.append(
            f"No reply is linked to a message, so the last send before the "
            f"outcome is credited: step {message.step_no} on "
            f"{message.channel.value if message.channel else '?'}, "
            f"{hours:.0f}h earlier.")
        if len(sent) > 1:
            evidence.append(f"{len(sent)} messages had been sent by then; "
                            f"any of them may have done the work.")
        return {"message": message, "method": LAST_TOUCH,
                "confidence": last_touch_confidence(hours), "evidence": evidence}

    evidence.append("Nothing had been sent to this prospect before the outcome.")
    return {"message": None, "method": NONE, "confidence": 0.0, "evidence": evidence}


# --------------------------------------------------------------------------
# Recording
# --------------------------------------------------------------------------


def _owner_id(db: Session, lead: Lead | None):
    if lead is None:
        return None
    strategy = db.get(Strategy, lead.strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    return product.user_id if product else None


def record(db: Session, *, lead: Lead | None, outcome_kind: str, outcome_id,
           outcome_at: datetime, strategy_id=None) -> AttributionEntry | None:
    """Write (or return) the ledger entry for one outcome.

    Idempotent: the UNIQUE on (outcome_kind, outcome_id) means a second call,
    a retried sweep or two overlapping workers cannot double-credit.
    """
    existing = db.execute(select(AttributionEntry).where(
        AttributionEntry.outcome_kind == outcome_kind,
        AttributionEntry.outcome_id == outcome_id)).scalar_one_or_none()
    if existing is not None:
        return existing
    if lead is None:
        return None

    outcome_at = _aware(outcome_at) or _now()
    found = credit(db, lead.id, outcome_at)
    message = found["message"]
    sent_at = _aware(message.sent_at) if message else None

    entry = AttributionEntry(
        lead_id=lead.id,
        user_id=_owner_id(db, lead),
        strategy_id=strategy_id or lead.strategy_id,
        outcome_kind=outcome_kind,
        outcome_id=outcome_id,
        outcome_at=outcome_at,
        message_id=message.id if message else None,
        channel=(message.channel.value if message and message.channel else None),
        step_no=message.step_no if message else None,
        message_sent_at=sent_at,
        hours_to_outcome=(round((outcome_at - sent_at).total_seconds() / 3600, 2)
                          if sent_at else None),
        method=found["method"],
        confidence=found["confidence"],
        evidence_json=found["evidence"],
        subject_snapshot=(message.subject or "")[:500] if message else None,
        body_snapshot=message.body if message else None,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.execute(select(AttributionEntry).where(
            AttributionEntry.outcome_kind == outcome_kind,
            AttributionEntry.outcome_id == outcome_id)).scalar_one_or_none()
    return entry


def _is_positive_reply(db: Session, outcome: Outcome) -> bool:
    """A REPLIED outcome only earns a ledger entry when the reply was good.

    Uses Feature 1's label. An unclassified reply is NOT credited: crediting
    every reply would put "stop emailing me" in the same ledger as a booking,
    which is exactly the dishonesty this feature exists to remove.
    """
    if outcome.lead_id is None:
        return False
    replies = _replies_before(db, outcome.lead_id, _aware(outcome.ts) or _now())
    return any(r.intent_label == "interested" for r in replies)


def run_sweep(db: Session, now: datetime | None = None, limit: int = 500) -> dict:
    """Credit every outcome that has no ledger entry yet.

    Covers every path that can create an outcome -- the Calendly webhook, our
    own booking page, the reply router, meeting outcomes, the CRM deal sync --
    past and future, and back-fills history for free.
    """
    now = now or _now()
    credited = {str(row.outcome_id) for row in db.execute(
        select(AttributionEntry.outcome_id)).all() if row.outcome_id}
    counts = {"checked": 0, "recorded": 0, "skipped": 0, "failed": 0}

    outcomes = db.execute(
        select(Outcome)
        .where(Outcome.event.in_(list(CREDITED_EVENTS)), Outcome.lead_id.isnot(None))
        .order_by(Outcome.ts.desc())
        .limit(limit)
    ).scalars().all()

    for outcome in outcomes:
        counts["checked"] += 1
        if str(outcome.id) in credited:
            counts["skipped"] += 1
            continue
        try:
            kind = CREDITED_EVENTS[outcome.event]
            if kind == POSITIVE_REPLY and not _is_positive_reply(db, outcome):
                counts["skipped"] += 1
                continue
            lead = db.get(Lead, outcome.lead_id)
            entry = record(db, lead=lead, outcome_kind=kind, outcome_id=outcome.id,
                           outcome_at=_aware(outcome.ts) or now,
                           strategy_id=outcome.strategy_id)
            counts["recorded" if entry is not None else "skipped"] += 1
        except Exception:  # noqa: BLE001 -- one bad outcome must not stop the sweep
            counts["failed"] += 1
            logger.exception("attribution failed for outcome %s", outcome.id)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
    return counts


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def entry_out(db: Session, entry: AttributionEntry) -> dict:
    lead = db.get(Lead, entry.lead_id) if entry.lead_id else None
    return {
        "id": str(entry.id),
        "outcome_kind": entry.outcome_kind,
        "outcome_at": entry.outcome_at.isoformat() if entry.outcome_at else None,
        "lead": ({"id": str(lead.id), "full_name": lead.full_name,
                  "company": lead.company} if lead else None),
        "message_id": str(entry.message_id) if entry.message_id else None,
        "channel": entry.channel,
        "step_no": entry.step_no,
        "message_sent_at": (entry.message_sent_at.isoformat()
                            if entry.message_sent_at else None),
        "hours_to_outcome": entry.hours_to_outcome,
        "method": entry.method,
        "method_label": METHOD_LABELS.get(entry.method, entry.method),
        # Always shown. A ledger that hides how sure it is will be believed
        # when it should not be.
        "confidence": entry.confidence,
        "is_certain": entry.method == DIRECT_REPLY,
        "evidence": entry.evidence_json or [],
        "subject": entry.subject_snapshot,
        "body": entry.body_snapshot,
    }


def ledger(db: Session, user_id, *, outcome_kind: str | None = None,
           strategy_id=None, limit: int = 100, offset: int = 0) -> dict:
    query = select(AttributionEntry).where(AttributionEntry.user_id == user_id)
    if outcome_kind:
        query = query.where(AttributionEntry.outcome_kind == outcome_kind)
    if strategy_id:
        query = query.where(AttributionEntry.strategy_id == strategy_id)
    rows = list(db.execute(
        query.order_by(AttributionEntry.outcome_at.desc()).offset(offset).limit(limit)
    ).scalars())
    total = len(list(db.execute(
        query.with_only_columns(AttributionEntry.id)).all()))
    return {"total": total, "limit": limit, "offset": offset,
            "items": [entry_out(db, row) for row in rows]}


def for_lead(db: Session, lead_id) -> list[dict]:
    rows = db.execute(
        select(AttributionEntry)
        .where(AttributionEntry.lead_id == lead_id)
        .order_by(AttributionEntry.outcome_at.desc())).scalars()
    return [entry_out(db, row) for row in rows]


def summary(db: Session, user_id, strategy_id=None) -> dict:
    """What earned the outcomes, aggregated -- the answer to "which step
    actually works?".

    Every bucket carries its own `certain` count. An aggregate built mostly
    from last-touch guesses is a very different claim from one built from
    replies, and the caller should be able to see that without reading rows.
    """
    query = select(AttributionEntry).where(AttributionEntry.user_id == user_id)
    if strategy_id:
        query = query.where(AttributionEntry.strategy_id == strategy_id)
    rows = list(db.execute(query).scalars())

    by_step: dict = {}
    by_channel: dict = {}
    by_method = {name: 0 for name in METHODS}
    for row in rows:
        by_method[row.method] = by_method.get(row.method, 0) + 1
        certain = row.method == DIRECT_REPLY
        if row.step_no is not None:
            bucket = by_step.setdefault(row.step_no, {"step_no": row.step_no,
                                                      "count": 0, "certain": 0})
            bucket["count"] += 1
            bucket["certain"] += int(certain)
        if row.channel:
            bucket = by_channel.setdefault(row.channel, {"channel": row.channel,
                                                         "count": 0, "certain": 0})
            bucket["count"] += 1
            bucket["certain"] += int(certain)

    hours = [r.hours_to_outcome for r in rows if r.hours_to_outcome is not None]
    return {
        "total": len(rows),
        "certain": by_method.get(DIRECT_REPLY, 0),
        "by_step": sorted(by_step.values(), key=lambda b: -b["count"]),
        "by_channel": sorted(by_channel.values(), key=lambda b: -b["count"]),
        "by_method": [{"method": name, "label": METHOD_LABELS[name],
                       "count": by_method.get(name, 0)} for name in METHODS],
        "median_hours_to_outcome": (sorted(hours)[len(hours) // 2] if hours else None),
    }
