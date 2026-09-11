"""Per-step conversion funnel (Feature Group 3): where does a campaign convert,
and where do leads drop off?

For every step of every sequence in the campaign:
  sent         leads that step was sent to
  opened       of those messages, how many were opened (email pixel or
               WhatsApp read receipt -- NULL rate for channels with neither)
  replied      leads whose reply is attributed to this step
  booked       leads whose booking is attributed to this step
  dropped      leads for whom this was the LAST step they got, who never
               replied or booked, and whose enrollment has ended
  in_progress  leads whose last step so far is this one and who are still
               enrolled (waiting for the next step -- not a drop-off yet)

ATTRIBUTION
An outcome that carries its message_id belongs to that message's step. One
that does not (a booking from a Calendly link, a reply matched by address)
belongs to the latest step sent to that lead before the outcome happened --
the message the lead was most plausibly responding to.
"""

from __future__ import annotations

import bisect
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChannelType,
    EnrollmentStatus,
    Lead,
    Message,
    Outcome,
    OutcomeEvent,
    Sequence,
    SequenceEnrollment,
)

BEST_STEP_MIN_SENT = 20
_OPEN_CHANNELS = {"email", "whatsapp"}


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _channel(value) -> str:
    return value.value if isinstance(value, ChannelType) else str(value)


def step_funnel(session: Session, strategy_id) -> dict:
    sequences = session.execute(
        select(Sequence).where(Sequence.strategy_id == strategy_id)
        .order_by(Sequence.created_at)
    ).scalars().all()
    seq_ids = [s.id for s in sequences]
    if not seq_ids:
        return {"sequences": [], "best_step": None}

    sent_rows = session.execute(
        select(Message.id, Message.sequence_id, Message.lead_id, Message.step_no,
               Message.sent_at, Message.opened_at)
        .where(Message.sequence_id.in_(seq_ids), Message.sent_at.isnot(None))
    ).all()
    by_id = {r.id: r for r in sent_rows}
    per_lead: dict = {}
    for r in sent_rows:
        per_lead.setdefault(r.lead_id, []).append((_aware(r.sent_at), r))
    for items in per_lead.values():
        items.sort(key=lambda t: t[0])

    def attribute(lead_id, message_id, ts):
        if message_id in by_id:
            return by_id[message_id]
        items = per_lead.get(lead_id) or []
        if not items:
            return None
        if ts is None:
            return items[-1][1]
        idx = bisect.bisect_right([t for t, _ in items], _aware(ts))
        return items[idx - 1][1] if idx else None

    stats: dict = {}

    def cell(seq_id, step_no) -> dict:
        return stats.setdefault((seq_id, step_no), {
            "sent": set(), "opened": set(), "replied": set(), "booked": set(),
            "dropped": 0, "in_progress": 0})

    for r in sent_rows:
        c = cell(r.sequence_id, r.step_no)
        c["sent"].add(r.lead_id)
        if r.opened_at is not None:
            c["opened"].add(r.id)

    outcomes = session.execute(
        select(Outcome.lead_id, Outcome.message_id, Outcome.event, Outcome.ts)
        .join(Lead, Lead.id == Outcome.lead_id)
        .where(Lead.strategy_id == strategy_id,
               Outcome.event.in_([OutcomeEvent.OPENED, OutcomeEvent.REPLIED,
                                  OutcomeEvent.BOOKED]))
    ).all()
    converted: set = set()   # (sequence_id, lead_id) that replied or booked
    for lead_id, message_id, event, ts in outcomes:
        msg = attribute(lead_id, message_id, ts)
        if msg is None:
            continue
        c = cell(msg.sequence_id, msg.step_no)
        if event is OutcomeEvent.OPENED:
            c["opened"].add(msg.id)
        else:
            c["replied" if event is OutcomeEvent.REPLIED else "booked"].add(lead_id)
            converted.add((msg.sequence_id, lead_id))

    enrollment_status = {
        (seq_id, lead_id): status for seq_id, lead_id, status in session.execute(
            select(SequenceEnrollment.sequence_id, SequenceEnrollment.lead_id,
                   SequenceEnrollment.status)
            .where(SequenceEnrollment.sequence_id.in_(seq_ids))
        ).all()
    }
    last_step: dict = {}
    for r in sent_rows:
        key = (r.sequence_id, r.lead_id)
        last_step[key] = max(last_step.get(key, 0), r.step_no)
    for key, step_no in last_step.items():
        if key in converted:
            continue
        status = enrollment_status.get(key)
        c = cell(key[0], step_no)
        if status in (EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED):
            c["in_progress"] += 1
        else:
            c["dropped"] += 1

    out_sequences = []
    best = None
    for seq in sequences:
        steps = []
        for step in seq.steps:
            channel = _channel(step.effective_channel(seq))
            c = stats.get((seq.id, step.step_no)) or cell(seq.id, step.step_no)
            sent = len(c["sent"])
            row = {
                "step_no": step.step_no, "channel": channel, "variant": step.variant,
                "sent": sent, "opened": len(c["opened"]), "replied": len(c["replied"]),
                "booked": len(c["booked"]), "dropped": c["dropped"],
                "in_progress": c["in_progress"],
                "open_rate": _rate(len(c["opened"]), sent) if channel in _OPEN_CHANNELS else None,
                "reply_rate": _rate(len(c["replied"]), sent),
                "booking_rate": _rate(len(c["booked"]), sent),
                "drop_off_rate": _rate(c["dropped"], sent),
            }
            steps.append(row)
            if sent >= BEST_STEP_MIN_SENT and row["reply_rate"] is not None and (
                    best is None or row["reply_rate"] > best["reply_rate"]):
                best = {"sequence_id": str(seq.id), "sequence_name": seq.name,
                        "step_no": step.step_no, "reply_rate": row["reply_rate"]}
        out_sequences.append({"id": str(seq.id), "name": seq.name,
                              "channel": _channel(seq.channel), "steps": steps})
    return {"sequences": out_sequences, "best_step": best,
            "best_step_min_sent": BEST_STEP_MIN_SENT}
