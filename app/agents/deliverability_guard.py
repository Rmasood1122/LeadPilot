"""Agent 3 -- Deliverability Guard (C++ core: native/cpp/src/deliverability.cpp).

Per connected mailbox, last 30 days: bounce, opt-out and reply rates, a
Wilson lower bound for the drastic call, the warm-up ramp, a risk level
(insufficient_data | healthy | elevated | critical) and a recommended daily
cap. Recommends only; the configured caps and app/services/mailbox_health.py
keep governing what is actually sent.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents import native
from app.agents.base import AgentResult, aware, now, owned_lead_ids
from app.config import settings
from app.db.models import (
    GmailAccount, InboundReply, Message, MessageStatus, Outcome, OutcomeEvent, User,
)

NAME = "deliverability_guard"
WINDOW_DAYS = 30


def run(db: Session, user: User, params: dict) -> AgentResult:
    t = now()
    since = t - timedelta(days=WINDOW_DAYS)
    owned = owned_lead_ids(user)
    mailboxes = db.execute(select(GmailAccount).where(GmailAccount.user_id == user.id)
                           .order_by(GmailAccount.created_at)).scalars().all()
    out = []
    for box in mailboxes:
        sent_ids = (select(Message.id)
                    .where(Message.sender_ref == str(box.id), Message.lead_id.in_(owned),
                           Message.sent_at >= since,
                           Message.status.in_([MessageStatus.SENT, MessageStatus.BOUNCED])))
        sent = db.execute(select(func.count()).select_from(sent_ids.subquery())).scalar_one()

        def outcomes(*events):
            return db.execute(select(func.count(Outcome.id)).where(
                Outcome.message_id.in_(sent_ids), Outcome.event.in_(events))).scalar_one()

        bounced = outcomes(OutcomeEvent.BOUNCED)
        unsub = outcomes(OutcomeEvent.UNSUBSCRIBED, OutcomeEvent.OPTED_OUT)
        replies = db.execute(select(func.count(InboundReply.id))
                             .where(InboundReply.message_id.in_(sent_ids))).scalar_one()
        age = (t - aware(box.created_at)).total_seconds() / 86400.0 if box.created_at else 0.0
        verdict = native.cpp.assess_mailbox(int(sent), int(bounced), int(unsub), int(replies),
                                            float(age), int(settings.gmail_daily_cap))
        out.append({"mailbox_id": str(box.id), "address": box.email_address,
                    "sent_30d": int(sent), "bounced_30d": int(bounced),
                    "opted_out_30d": int(unsub), "replies_30d": int(replies),
                    "age_days": round(age, 1), "configured_cap": int(settings.gmail_daily_cap),
                    **verdict})
    worst = {"critical": 3, "elevated": 2, "healthy": 1, "insufficient_data": 0}
    overall = max((m["risk"] for m in out), key=lambda r: worst[r], default="insufficient_data")
    return AgentResult(len(out), {"mailboxes": out, "overall_risk": overall})
