"""Human review queue for high-risk sends (Part 1, Feature 5).

WHY THIS EXISTS BESIDE adversarial_review.py. That feature reviews a
sequence's CONTENT once, before launch. This one reviews a MESSAGE, at send
time, because every trigger here is a fact about the prospect *at that moment*
that no pre-launch review of a template could know:

  PRIOR_OBJECTION  they pushed back on the last message. Sending the next
                   scheduled step into an objection is how a recoverable "not
                   convinced" becomes "stop emailing me".
  DEAL_STALLED     there is money on this relationship and it has gone quiet.
                   A templated nudge is the wrong instrument.
  VIP_TITLE        a founder, C-level or VP. One badly judged line costs the
                   whole account, and there are few enough of them that a
                   person can read every message.
  TONE_FLAG        the rendered copy tripped the shared tone/spam rules
                   (adversarial_review._text_findings, reused verbatim so the
                   pre-launch gate and this one cannot disagree about what
                   reads badly).

WHAT HOLDING MEANS. The message is rendered, persisted, and moved to
MessageStatus.AWAITING_REVIEW. It is QUEUED, NOT LOST: approving returns it to
SCHEDULED and the next dispatch tick sends it. Nothing is deleted and no step
is skipped, so Feature 3's completion guarantee is unaffected.

WHAT THE REVIEWER APPROVES IS WHAT SENDS -- LITERALLY. The exact subject and
body are snapshotted when the message is held, and an approved review sends
THAT TEXT, discarding whatever the next render produced.

That rule is not a convenience, it is the only correct one here. Rendering is a
model call: the same step, the same lead and the same brief produce different
words on every pass. If the send path re-rendered after approval and compared,
the copy would differ every time and the message would loop in the queue
forever, never sending. Snapshot-is-authoritative also means a person can point
at the sent message and at the approval and see the same words.

A reviewer may EDIT the copy, and the edit is what transmits -- the point of a
human gate is that the human can improve the message, not only veto it.
`content_hash` is kept as the record of what was signed off.
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid as uuid_module
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Deal,
    DealStage,
    InboundReply,
    Lead,
    Message,
    MessageStatus,
    Product,
    SendReview,
    Strategy,
)

logger = logging.getLogger(__name__)

PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"

PRIOR_OBJECTION = "prior_objection"
DEAL_STALLED = "deal_stalled"
VIP_TITLE = "vip_title"
TONE_FLAG = "tone_flag"

TRIGGERS = (PRIOR_OBJECTION, DEAL_STALLED, VIP_TITLE, TONE_FLAG)

LABELS = {
    PRIOR_OBJECTION: "Prospect objected before",
    DEAL_STALLED: "Deal has stalled",
    VIP_TITLE: "Executive / VIP contact",
    TONE_FLAG: "Tone or spam check flagged the copy",
}

#: Titles that make one badly judged line expensive. Deliberately narrow:
#: widening this to every "manager" would put the whole campaign in the queue
#: and the queue would stop being read.
_VIP_TITLE = re.compile(
    r"\b(founder|co-?founder|owner|ceo|coo|cfo|cto|cmo|cro|chief\s+\w+|"
    r"president|managing\s+director|partner|vp|vice\s+president|"
    r"head\s+of|board\s+member|chair(man|woman|person)?)\b", re.I)

#: An OPEN deal whose expected close date has passed is "stalled". The schema
#: has no stalled stage (DealStage is open/won/lost), and inventing one would
#: mean migrating a column every consumer already reads. A close date in the
#: past on an open deal is the same fact, already recorded.
STALLED_GRACE_DAYS = 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def content_hash(subject: str | None, body: str | None) -> str:
    payload = f"{(subject or '').strip()}\n\n{(body or '').strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# The triggers
# --------------------------------------------------------------------------


def _trigger(code: str, detail: str) -> dict:
    return {"code": code, "label": LABELS[code], "detail": detail[:300]}


def prior_objection(db: Session, lead: Lead) -> dict | None:
    """Did this prospect push back on an earlier message?

    Reads BOTH classifiers, because they were built for different questions
    and either one alone would miss cases: `reply_category == "OBJECTION"`
    (FG1) and `intent_label == "objection"` (Part 1 Feature 1).
    """
    reply = db.execute(
        select(InboundReply)
        .where(InboundReply.lead_id == lead.id)
        .order_by(InboundReply.created_at.desc())
    ).scalars().first()
    if reply is None:
        return None
    if (reply.reply_category or "").upper() == "OBJECTION" or reply.intent_label == "objection":
        excerpt = " ".join((reply.body or "").split())[:160]
        return _trigger(PRIOR_OBJECTION,
                        f'Their last reply was an objection: "{excerpt}"' if excerpt
                        else "Their last reply was classified as an objection.")
    return None


def deal_stalled(db: Session, lead: Lead, now: datetime) -> dict | None:
    """An open deal whose expected close date has passed."""
    deals = db.execute(
        select(Deal).where(Deal.lead_id == lead.id, Deal.stage == DealStage.OPEN)
    ).scalars().all()
    today = now.astimezone(timezone.utc).date()
    for deal in deals:
        if deal.close_date and deal.close_date < today:
            return _trigger(DEAL_STALLED,
                            f'"{deal.name}" was due to close on '
                            f"{deal.close_date.isoformat()} and is still open.")
    # A lead the conversion sweep has cooled is the same signal from the other
    # direction: something was live here and has gone quiet.
    if lead.engagement_state == "cooling":
        return _trigger(DEAL_STALLED,
                        "The conversion sweep marked this prospect as cooling.")
    return None


def vip_title(lead: Lead) -> dict | None:
    match = _VIP_TITLE.search(lead.title or "")
    if not match:
        return None
    return _trigger(VIP_TITLE,
                    f"{lead.full_name or 'This contact'} is {lead.title} at "
                    f"{lead.company or 'their company'}.")


def tone_flags(subject: str | None, body: str | None, channel: str) -> dict | None:
    """The shared tone/spam rules, over the RENDERED copy.

    `adversarial_review._text_findings` is reused verbatim rather than
    reimplemented, so the pre-launch gate and this one can never disagree
    about what reads badly. Only block/warn findings in the tone and spam
    categories hold a message -- a compliance finding is already handled by
    the compliance layer, and a claim finding is stripped by the claim engine.
    """
    from app.services import adversarial_review  # noqa: PLC0415

    text = f"{subject or ''}\n{body or ''}"
    findings = [f for f in adversarial_review._text_findings(text, None, channel=channel)
                if f["category"] in ("tone", "spam")]
    if not findings:
        return None
    worst = sorted(findings, key=lambda f: 0 if f["severity"] == "block" else 1)
    return _trigger(TONE_FLAG, "; ".join(f["message"] for f in worst[:3]))


#: Which admin setting switches each trigger. Separately switchable because
#: which triggers are useful depends entirely on the ICP -- see the note in
#: system_settings.DEFAULTS about selling TO founders.
SETTING_FOR = {
    PRIOR_OBJECTION: "send_review_prior_objection",
    DEAL_STALLED: "send_review_stalled_deal",
    VIP_TITLE: "send_review_vip_titles",
    TONE_FLAG: "send_review_tone",
}


def enabled(db: Session, code: str | None = None) -> bool:
    """Is the queue on, and is this particular trigger on?

    Defaults to True on any failure reading the settings: the safe direction
    for a REVIEW gate is to review.
    """
    from app.services import system_settings  # noqa: PLC0415

    try:
        if not system_settings.get(db, "send_review_enabled"):
            return False
        return True if code is None else bool(system_settings.get(db, SETTING_FOR[code]))
    except Exception:  # noqa: BLE001
        logger.exception("could not read send-review settings — assuming enabled")
        return True


def evaluate(db: Session, lead: Lead, subject: str | None, body: str | None,
             channel: str, now: datetime | None = None) -> list[dict]:
    """Every reason this message needs a person, in the order they are shown.

    Never raises: an evaluation failure must not block a send that would
    otherwise be fine. It logs and returns what it managed to compute, which
    fails OPEN on purpose -- holding every message because a query broke would
    stop the product dead.
    """
    now = now or _now()
    if not enabled(db):
        return []
    out: list[dict] = []
    for code, check in (
        (PRIOR_OBJECTION, lambda: prior_objection(db, lead)),
        (DEAL_STALLED, lambda: deal_stalled(db, lead, now)),
        (VIP_TITLE, lambda: vip_title(lead)),
        (TONE_FLAG, lambda: tone_flags(subject, body, channel)),
    ):
        if not enabled(db, code):
            continue
        try:
            found = check()
        except Exception:  # noqa: BLE001 -- see the docstring
            logger.exception("send-review trigger check failed for lead %s", lead.id)
            continue
        if found:
            out.append(found)
    return out


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def _owner_id(db: Session, lead: Lead):
    strategy = db.get(Strategy, lead.strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    return product.user_id if product else None


def review_for(db: Session, message_id) -> SendReview | None:
    return db.execute(
        select(SendReview).where(SendReview.message_id == message_id)).scalar_one_or_none()


def gate(db: Session, lead: Lead, message: Message, subject: str | None,
         body: str | None, now: datetime | None = None) -> dict:
    """The decision the send path acts on, called AFTER the copy is rendered.

    RETURNS one of
      {"action": "send",  "subject": ..., "body": ...}   proceed. For an
          approved review these are the APPROVED words (or the reviewer's
          edit), not the freshly rendered ones -- see the module docstring.
      {"action": "hold",  "review": SendReview}          held for approval
      {"action": "cancel","reason": str}                 a reviewer rejected it

    Never raises. On any internal failure it returns "send": a broken review
    system must not silently stop outreach, and the triggers are a safety net
    over an already-compliant pipeline, not the compliance layer itself.
    """
    now = now or _now()
    try:
        existing = review_for(db, message.id)
        current = content_hash(subject, body)

        if existing is not None and existing.status == APPROVED:
            # The APPROVED words send, not the ones this pass just rendered.
            # Rendering is a model call and never repeats itself, so comparing
            # the two would re-queue the message on every attempt and it would
            # never go out. See the module docstring.
            return {"action": "send",
                    "subject": existing.edited_subject or existing.subject_snapshot,
                    "body": existing.edited_body or existing.body_snapshot}

        if existing is not None and existing.status == REJECTED:
            return {"action": "cancel",
                    "reason": existing.decision_note or "rejected in the review queue"}

        if existing is not None and existing.status == PENDING:
            return {"action": "hold", "review": existing}

        triggers = evaluate(db, lead, subject, body, message.channel.value, now)
        if not triggers:
            return {"action": "send", "subject": subject, "body": body}

        review = SendReview(message_id=message.id, lead_id=lead.id,
                            user_id=_owner_id(db, lead), status=PENDING,
                            triggers_json=triggers)
        _snapshot(review, subject, body, current)
        db.add(review)
        db.commit()
        _notify(db, review, lead)
        return {"action": "hold", "review": review}
    except Exception:  # noqa: BLE001 -- see the docstring
        logger.exception("send review gate failed for message %s — sending",
                         getattr(message, "id", None))
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"action": "send", "subject": subject, "body": body}


def _snapshot(review: SendReview, subject: str | None, body: str | None, digest: str) -> None:
    review.subject_snapshot = (subject or "")[:500] or None
    review.body_snapshot = body
    review.content_hash = digest


def _notify(db: Session, review: SendReview, lead: Lead) -> None:
    """Never raises: a notification failure must not undo a hold."""
    try:
        from app.workers import notification_tasks  # noqa: PLC0415

        if review.user_id is None:
            return
        labels = ", ".join(t["label"] for t in (review.triggers_json or []))
        notification_tasks.enqueue_event(
            review.user_id, "send_needs_review",
            title=f"A message to {lead.full_name or lead.email or 'a prospect'} needs approval",
            body=labels or "This send matched a high-risk rule.",
            deep_link="/campaigns?tab=review",
            data={"review_id": str(review.id), "lead_id": str(lead.id)},
            webhook_payload={"review_id": str(review.id), "lead_id": str(lead.id),
                             "triggers": [t["code"] for t in (review.triggers_json or [])]})
    except Exception:  # noqa: BLE001 -- see the docstring
        logger.exception("could not notify send review %s", review.id)


# --------------------------------------------------------------------------
# Decisions
# --------------------------------------------------------------------------


def approve(db: Session, review: SendReview, *, actor_user_id=None, note: str | None = None,
            subject: str | None = None, body: str | None = None,
            now: datetime | None = None) -> SendReview:
    """Approve, optionally with an edit, and return the message to the queue.

    Editing re-hashes: what the reviewer read and changed is what the send
    path will check against before transmitting.
    """
    now = now or _now()
    review.status = APPROVED
    review.decided_at = now
    review.decided_by_user_id = (actor_user_id
                                 if isinstance(actor_user_id, uuid_module.UUID)
                                 else uuid_module.UUID(str(actor_user_id))) if actor_user_id else None
    review.decision_note = (note or "")[:500] or None
    if subject is not None or body is not None:
        review.edited_subject = (subject if subject is not None
                                 else review.subject_snapshot)
        review.edited_body = body if body is not None else review.body_snapshot
        review.content_hash = content_hash(review.subject_snapshot, review.body_snapshot)

    message = db.get(Message, review.message_id)
    if message is not None and message.status is MessageStatus.AWAITING_REVIEW:
        # Back into the ordinary queue. The next dispatch tick sends it, and
        # the gate above will let it through because the hash matches.
        message.status = MessageStatus.SCHEDULED
        message.scheduled_at = now
        message.error = None
    db.commit()
    return review


def reject(db: Session, review: SendReview, *, actor_user_id=None, note: str | None = None,
           now: datetime | None = None) -> SendReview:
    """Reject: this message is never sent.

    The message is CANCELLED, not skipped, and the enrollment is left running
    -- rejecting one badly-timed email should not end the relationship. The
    next step is scheduled by the ordinary engine rules.
    """
    now = now or _now()
    review.status = REJECTED
    review.decided_at = now
    review.decided_by_user_id = (actor_user_id
                                 if isinstance(actor_user_id, uuid_module.UUID)
                                 else uuid_module.UUID(str(actor_user_id))) if actor_user_id else None
    review.decision_note = (note or "")[:500] or None

    message = db.get(Message, review.message_id)
    if message is not None and message.status in (MessageStatus.AWAITING_REVIEW,
                                                  MessageStatus.SCHEDULED):
        message.status = MessageStatus.CANCELLED
        message.error = f"rejected in review: {review.decision_note or 'no reason given'}"
    db.commit()
    return review


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def review_out(db: Session, review: SendReview) -> dict:
    lead = db.get(Lead, review.lead_id) if review.lead_id else None
    message = db.get(Message, review.message_id)
    return {
        "id": str(review.id),
        "message_id": str(review.message_id),
        "status": review.status,
        "triggers": review.triggers_json or [],
        "subject": review.edited_subject or review.subject_snapshot,
        "body": review.edited_body or review.body_snapshot,
        "edited": bool(review.edited_body or review.edited_subject),
        "channel": message.channel.value if message else None,
        "step_no": message.step_no if message else None,
        "message_status": message.status.value if message else None,
        "lead": ({"id": str(lead.id), "full_name": lead.full_name, "title": lead.title,
                  "company": lead.company, "email": lead.email} if lead else None),
        "decision_note": review.decision_note,
        "decided_at": review.decided_at.isoformat() if review.decided_at else None,
        "decided_by_user_id": (str(review.decided_by_user_id)
                               if review.decided_by_user_id else None),
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }


def queue(db: Session, user_id, *, status: str = PENDING, limit: int = 50,
          offset: int = 0) -> dict:
    """One user's review queue, oldest first — a queue, not a feed. The
    message that has been waiting longest is the one most at risk of going
    stale."""
    base = select(SendReview).where(SendReview.user_id == user_id)
    if status != "all":
        base = base.where(SendReview.status == status)
    rows = db.execute(
        base.order_by(SendReview.created_at.asc()).offset(offset).limit(limit)
    ).scalars().all()
    total = len(db.execute(
        select(SendReview.id).where(SendReview.user_id == user_id)
        .where(SendReview.status == status) if status != "all"
        else select(SendReview.id).where(SendReview.user_id == user_id)).all())
    return {"total": total, "limit": limit, "offset": offset, "status": status,
            "items": [review_out(db, row) for row in rows]}


def pending_count(db: Session, user_id) -> int:
    return len(db.execute(
        select(SendReview.id).where(SendReview.user_id == user_id,
                                    SendReview.status == PENDING)).all())
