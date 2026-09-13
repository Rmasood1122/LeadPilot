"""The unified cross-channel conversation with one lead (Feature A4).

One chronological timeline of everything that passed between the account and
a lead, whatever the channel:

  message             an outreach send (email, LinkedIn, WhatsApp, a call's
                      dial message) -- sent, bounced, failed or still scheduled
  reply               an inbound reply on any channel, with its authenticity
  call                an AI phone call: outcome, duration, summary
  booking             a slot booked on the native calendar
  meeting             a meeting held (or scheduled) with them
  channel_suggestion  the stagnation step's recommendation, and its decision

A READ MODEL, NOT A COPY. Every item is assembled from the table that owns it,
at read time, so the thread can never disagree with the send log, the inbox
or the call history -- the "two implementations of one concern" failure this
codebase keeps finding. `ThreadItem` in app/api/conversations.py is the typed
shape of one entry.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CalendarBooking,
    Call,
    ChannelSuggestion,
    InboundReply,
    Lead,
    Meeting,
    Message,
    MessageStatus,
)

_SKIP_STATUSES = {MessageStatus.CANCELLED}
_NOT_A_REAL_REPLY = {"automated_response", "out_of_office", "bounce"}


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return value.isoformat() if value else None


def _value(enum_or_str) -> str | None:
    return getattr(enum_or_str, "value", enum_or_str)


def build_thread(session: Session, lead: Lead, limit: int = 500) -> dict:
    entries: list[tuple[datetime, dict]] = []

    for msg in session.execute(select(Message).where(Message.lead_id == lead.id)).scalars():
        if msg.status in _SKIP_STATUSES:
            continue
        at = _aware(msg.sent_at or msg.scheduled_at or msg.created_at)
        scheduled = msg.status is MessageStatus.SCHEDULED
        entries.append((at, {
            "id": f"message:{msg.id}", "kind": "message", "direction": "outbound",
            "channel": _value(msg.channel), "at": _iso(at), "status": _value(msg.status),
            "subject": msg.subject, "body": None if scheduled else (msg.body or "")[:4000],
            "step_no": msg.step_no, "opened": msg.opened_at is not None,
            "open_count": msg.open_count or 0, "error": msg.error if not scheduled else None,
        }))

    for reply in session.execute(
            select(InboundReply).where(InboundReply.lead_id == lead.id)).scalars():
        at = _aware(reply.received_at or reply.created_at)
        entries.append((at, {
            "id": f"reply:{reply.id}", "kind": "reply", "direction": "inbound",
            "channel": reply.channel, "at": _iso(at), "subject": reply.subject,
            "body": (reply.body or "")[:4000], "classification": reply.classification,
            "authenticity": ({"kind": reply.authenticity_kind,
                              "buyer_intent_score": reply.buyer_intent_score,
                              "confidence": reply.authenticity_confidence}
                             if reply.authenticity_kind else None),
        }))

    for call in session.execute(select(Call).where(Call.lead_id == lead.id)).scalars():
        at = _aware(call.started_at or call.created_at)
        analysis = call.analysis_json or {}
        entries.append((at, {
            "id": f"call:{call.id}", "kind": "call", "direction": "outbound",
            "channel": "phone", "at": _iso(at), "status": call.status,
            "outcome": _value(call.outcome), "duration_seconds": call.duration_seconds,
            "body": analysis.get("summary") or (call.script_json or {}).get("first_message"),
        }))

    for booking in session.execute(
            select(CalendarBooking).where(CalendarBooking.lead_id == lead.id)).scalars():
        at = _aware(booking.created_at)
        entries.append((at, {
            "id": f"booking:{booking.id}", "kind": "booking", "direction": "inbound",
            "channel": "calendar", "at": _iso(at), "status": _value(booking.status),
            "starts_at": _iso(booking.start_at), "body": booking.notes,
        }))

    for meeting in session.execute(select(Meeting).where(Meeting.lead_id == lead.id)).scalars():
        at = _aware(meeting.actual_start_at or meeting.start_at)
        entries.append((at, {
            "id": f"meeting:{meeting.id}", "kind": "meeting", "direction": "both",
            "channel": "meeting", "at": _iso(at), "status": _value(meeting.status),
            "subject": meeting.title, "body": meeting.summary,
        }))

    for suggestion in session.execute(
            select(ChannelSuggestion).where(ChannelSuggestion.lead_id == lead.id)).scalars():
        at = _aware(suggestion.created_at)
        entries.append((at, {
            "id": f"suggestion:{suggestion.id}", "kind": "channel_suggestion",
            "direction": "system", "channel": suggestion.to_channel, "at": _iso(at),
            "status": suggestion.status, "from_channel": suggestion.from_channel,
            "suggestion_id": str(suggestion.id), "body": suggestion.reason,
        }))

    floor = datetime.min.replace(tzinfo=timezone.utc)
    entries.sort(key=lambda pair: (pair[0] or floor, pair[1]["id"]))
    items = [item for _, item in entries][-limit:]
    return {"lead_id": str(lead.id), "items": items, "summary": _summary(items)}


def _summary(items: list[dict]) -> dict:
    outbound: Counter = Counter()
    inbound: Counter = Counter()
    last_in = last_out = None
    for item in items:
        if item["kind"] in ("message", "call") and item.get("status") not in ("scheduled",):
            outbound[item["channel"]] += 1
            last_out = item["at"] or last_out
        if item["kind"] == "reply" and item.get("classification") not in _NOT_A_REAL_REPLY:
            inbound[item["channel"]] += 1
            last_in = item["at"] or last_in
    channels = sorted(set(outbound) | set(inbound))
    return {
        "channels": [{"channel": ch, "outbound": outbound[ch], "inbound": inbound[ch]}
                     for ch in channels],
        "last_outbound_at": last_out, "last_inbound_at": last_in,
        "open_suggestions": sum(1 for i in items if i["kind"] == "channel_suggestion"
                                and i.get("status") == "suggested"),
    }
