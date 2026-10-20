"""Agent 5 -- Claim & Compliance Check (C++ core: native/cpp/src/claims.cpp).

Scans the account's not-yet-sent email drafts (scheduled or awaiting review)
for guarantees, superlatives, unsourced numbers, false urgency, spam triggers,
a "Re:"/"Fwd:" subject on a first touch, a shouting subject and stacked
exclamation marks. `check_text` serves the ad-hoc endpoint. Advisory: the
send-time claim verification and guardrails remain the gates.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import native
from app.agents.base import AgentResult, int_param, owned_lead_ids
from app.db.models import ChannelType, Message, MessageStatus, User

NAME = "claim_check"
_PENDING = (MessageStatus.SCHEDULED, MessageStatus.AWAITING_REVIEW)


def check_text(subject: str, body: str, first_touch: bool) -> dict:
    return native.cpp.check_claims(subject or "", body or "", bool(first_touch))


def run(db: Session, user: User, params: dict) -> AgentResult:
    limit = int_param(params, "limit", 200, 1, 500)
    drafts = db.execute(
        select(Message).where(Message.lead_id.in_(owned_lead_ids(user)),
                              Message.status.in_(_PENDING),
                              Message.channel == ChannelType.EMAIL)
        .order_by(Message.scheduled_at.asc().nulls_last(), Message.id).limit(limit)
    ).scalars().all()
    flagged, verdicts = [], {}
    for msg in drafts:
        report = check_text(msg.subject or "", msg.body or "", msg.step_no == 1)
        verdicts[report["verdict"]] = verdicts.get(report["verdict"], 0) + 1
        if report["verdict"] != "pass":
            flagged.append({"message_id": str(msg.id), "lead_id": str(msg.lead_id),
                            "step_no": msg.step_no, "subject": msg.subject, **report})
    flagged.sort(key=lambda f: (-f["risk"], f["message_id"]))
    return AgentResult(len(drafts), {"checked": len(drafts), "verdicts": verdicts,
                                     "flagged": flagged})
