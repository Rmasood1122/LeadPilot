"""Agent 1 -- Lead Priority (Rust core: native/rust/src/scoring.rs).

Ranks the account's leads by who to work next and says what to do with each:
respond_now, follow_up_now, start_sequence, nurture, rest, do_not_contact.
Fit is the existing lead score (ai_booking_likelihood, 0-100); engagement is
opens/clicks decayed with a 7-day half-life; fatigue grows with sent touches.
A suppressed, unsubscribed or bounced lead is always do_not_contact.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import native
from app.agents.base import AgentResult, aware, int_param, now, owned_lead_ids
from app.db.models import (
    Lead, LeadStatus, Message, MessageStatus, Outcome, OutcomeEvent, SuppressionEntry, User,
)

NAME = "lead_priority"
_ENGAGED = (OutcomeEvent.OPENED, OutcomeEvent.CLICKED, OutcomeEvent.REPLIED)
_STOPPED = (OutcomeEvent.UNSUBSCRIBED, OutcomeEvent.OPTED_OUT)
MAX_LEADS = 2000


def _strategy_id(params: dict):
    raw = params.get("strategy_id")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except ValueError:
        raise ValueError("strategy_id must be a UUID") from None


def run(db: Session, user: User, params: dict) -> AgentResult:
    limit = int_param(params, "limit", 50, 1, 200)
    owned = owned_lead_ids(user, _strategy_id(params))
    leads = db.execute(select(Lead).where(Lead.id.in_(owned))
                       .order_by(Lead.created_at.desc()).limit(MAX_LEADS)).scalars().all()
    if not leads:
        return AgentResult(0, {"leads": [], "actions": {}})
    ids = [lead.id for lead in leads]

    events: dict = {}
    for lead_id, event, count, last in db.execute(
            select(Outcome.lead_id, Outcome.event, func.count(Outcome.id), func.max(Outcome.ts))
            .where(Outcome.lead_id.in_(ids)).group_by(Outcome.lead_id, Outcome.event)):
        events.setdefault(lead_id, {})[event] = (count, aware(last))
    touches = {lead_id: (count, aware(last)) for lead_id, count, last in db.execute(
        select(Message.lead_id, func.count(Message.id), func.max(Message.sent_at))
        .where(Message.lead_id.in_(ids), Message.status == MessageStatus.SENT)
        .group_by(Message.lead_id))}
    emails = {lead.email.lower() for lead in leads if lead.email}
    suppressed = set()
    if emails:
        suppressed = {e for (e,) in db.execute(
            select(func.lower(SuppressionEntry.email))
            .where(func.lower(SuppressionEntry.email).in_(emails)))}

    t = now()

    def days(dt):
        return (t - dt).total_seconds() / 86400.0 if dt else -1.0

    signals = []
    for lead in leads:
        ev = events.get(lead.id, {})
        opens = ev.get(OutcomeEvent.OPENED, (0, None))[0]
        clicks = ev.get(OutcomeEvent.CLICKED, (0, None))[0]
        engaged_at = [ev[e][1] for e in _ENGAGED if e in ev and ev[e][1]]
        n_touch, last_touch = touches.get(lead.id, (0, None))
        fit = (lead.ai_booking_likelihood / 100.0
               if lead.ai_booking_likelihood is not None else 0.5)
        replied = OutcomeEvent.REPLIED in ev or lead.status is LeadStatus.REPLIED
        bounced = OutcomeEvent.BOUNCED in ev or lead.status is LeadStatus.DROPPED
        unsub = (any(e in ev for e in _STOPPED)
                 or bool(lead.email and lead.email.lower() in suppressed))
        signals.append((float(fit), int(opens), int(clicks), bool(replied), bool(bounced),
                        bool(unsub), int(n_touch), days(last_touch),
                        days(max(engaged_at)) if engaged_at else -1.0))

    scored = native.rs.prioritize_leads(signals)
    rows = []
    for lead, sig, (priority, action, engagement, fatigue) in zip(leads, signals, scored):
        rows.append({"lead_id": str(lead.id), "name": lead.full_name, "company": lead.company,
                     "title": lead.title, "priority": priority, "action": action,
                     "fit": round(sig[0], 3), "engagement": round(engagement, 3),
                     "fatigue": round(fatigue, 3), "touches": sig[6]})
    rows.sort(key=lambda r: (-r["priority"], r["lead_id"]))
    actions: dict[str, int] = {}
    for r in rows:
        actions[r["action"]] = actions.get(r["action"], 0) + 1
    return AgentResult(len(rows), {"leads": rows[:limit], "actions": actions})
