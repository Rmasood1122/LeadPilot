"""Agent 2 -- Follow-up Timing (Rust core: native/rust/src/timing.rs).

When this account's prospects actually reply (hour of the week, UTC), smoothed
with a business-hours prior, and the best next slot to follow up after a
minimum gap. Confidence grows with the number of replies seen: n / (n + 20).
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import native
from app.agents.base import AgentResult, aware, int_param, now, owned_lead_ids
from app.db.models import InboundReply, User

NAME = "followup_timing"
HISTORY_DAYS = 180
MAX_REPLIES = 5000
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def _slot(weekday: int, hour: int, weight: float) -> dict:
    return {"weekday": _DAYS[weekday], "hour_utc": hour, "weight": round(weight, 3)}


def run(db: Session, user: User, params: dict) -> AgentResult:
    min_gap = int_param(params, "min_gap_hours", 48, 0, 336)
    business_only = str(params.get("business_only", "true")).lower() not in ("0", "false", "no")
    t = now()
    stamps = db.execute(
        select(InboundReply.received_at, InboundReply.created_at)
        .where(InboundReply.lead_id.in_(owned_lead_ids(user)),
               InboundReply.created_at >= t - timedelta(days=HISTORY_DAYS))
        .order_by(InboundReply.created_at.desc()).limit(MAX_REPLIES)).all()
    replies = []
    for received, created in stamps:
        when = aware(received or created)
        replies.append((when.weekday(), when.hour))

    slot = native.rs.next_followup_slot(replies, t.weekday(), t.hour, min_gap, business_only)
    nxt = None
    if slot is not None:
        ahead, weekday, hour, weight, confidence = slot
        at = t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=ahead)
        nxt = {"at": at.isoformat(), "hours_ahead": ahead, **_slot(weekday, hour, weight),
               "confidence": round(confidence, 3)}
    top = [_slot(d, h, w) for d, h, w in native.rs.top_reply_slots(replies, 5)]
    return AgentResult(len(replies), {"replies_seen": len(replies), "next_slot": nxt,
                                      "top_slots": top, "min_gap_hours": min_gap,
                                      "business_only": business_only, "timezone": "UTC"})
