"""Agent 4 -- Reply Triage (C++ core: native/cpp/src/triage.cpp).

Re-reads the account's recent replies with a deterministic phrase model and
compares its answer with the stored classification. The point is the
disagreements: a reply this agent reads as an opt-out that the stored
classification did not file as one is listed under `needs_review`, so a
person can confirm it. Nothing is suppressed or re-filed here; the existing
reply classifier and suppression path stay authoritative.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import native
from app.agents.base import AgentResult, int_param, now, owned_lead_ids
from app.db.models import InboundReply, User

NAME = "reply_triage"
WINDOW_DAYS = 30
STORED_OPT_OUT = frozenset({"unsubscribe_request", "unsubscribe", "opt_out", "opted_out"})


def run(db: Session, user: User, params: dict) -> AgentResult:
    limit = int_param(params, "limit", 200, 1, 500)
    replies = db.execute(
        select(InboundReply)
        .where(InboundReply.lead_id.in_(owned_lead_ids(user)),
               InboundReply.created_at >= now() - timedelta(days=WINDOW_DAYS))
        .order_by(InboundReply.created_at.desc()).limit(limit)).scalars().all()
    rows, labels, needs_review = [], {}, []
    for reply in replies:
        t = native.cpp.triage_reply(reply.subject or "", reply.body or "")
        stored = (reply.classification or reply.reply_category or "").lower() or None
        row = {"reply_id": str(reply.id), "lead_id": str(reply.lead_id) if reply.lead_id else None,
               "label": t["label"], "confidence": round(t["confidence"], 3),
               "opt_out": t["opt_out"], "stored_classification": stored,
               "matched": [p for _, p in t["matched"]]}
        rows.append(row)
        labels[t["label"]] = labels.get(t["label"], 0) + 1
        if t["opt_out"] and stored not in STORED_OPT_OUT:
            needs_review.append(row)
    return AgentResult(len(rows), {"replies": rows, "labels": labels,
                                   "needs_review": needs_review})
