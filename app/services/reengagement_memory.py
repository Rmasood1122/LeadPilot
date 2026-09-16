"""Re-engagement memory: "not now" is not "never" (Part 1, Feature 7).

THE PROBLEM. A prospect who writes "we're mid-contract until March, try us
then" has just told you the single most valuable thing in cold outreach: a
date. Every outbound tool then does the same thing with it -- stops the
sequence, marks the lead as not interested, and forgets. March arrives and
nobody comes back, because nothing wrote it down.

WHAT THIS DOES. Every reply Feature 1 labels `not_now` produces a
ReengagementPlan carrying:
  * the reason IN THE PROSPECT'S OWN WORDS, so the return message can quote
    the sentence rather than paraphrase it nine months later;
  * a `reason_kind` (budget / contract / timing / project / headcount /
    priority) for grouping;
  * `stated_return_on` when they NAMED a date, which beats any default;
  * `due_at` -- their date if they gave one, otherwise today plus the
    configured interval (90 days by default).

WHEN THE DAY ARRIVES. The sweep marks the plan `due` and notifies. If
`reengagement_memory_auto_send` is on (the default), it also schedules a real
message through the ordinary send path -- so suppression, compliance, mailbox
health and the human review queue all still apply. Nothing here bypasses a
gate; it only decides WHEN to knock.

WHAT IT DOES NOT DO. It never resurrects a prospect who unsubscribed, bounced,
was suppressed, or has since replied with something better. Those are checked
at the moment the plan comes due, not when it was made -- 90 days is long
enough for all of them to have happened.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    InboundReply,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Product,
    ReengagementPlan,
    SequenceEnrollment,
    Strategy,
    SuppressionEntry,
)

logger = logging.getLogger(__name__)

SCHEDULED, DUE, SENT, CANCELLED = "scheduled", "due", "sent", "cancelled"

#: The message origin, so the send path and the analytics can tell a
#: memory touch from an ordinary step and from the 0048 sweep's touch.
ORIGIN = "notnow_memory"

DEFAULT_INTERVAL_DAYS = 90
MIN_INTERVAL_DAYS = 7
MAX_INTERVAL_DAYS = 540

BUDGET, CONTRACT, TIMING, PROJECT, HEADCOUNT, PRIORITY, UNSPECIFIED = (
    "budget", "contract", "timing", "project", "headcount", "priority", "unspecified")
REASON_KINDS = (BUDGET, CONTRACT, TIMING, PROJECT, HEADCOUNT, PRIORITY, UNSPECIFIED)

REASON_LABELS = {
    BUDGET: "No budget right now",
    CONTRACT: "Locked into a contract",
    TIMING: "Bad timing",
    PROJECT: "Busy with another project",
    HEADCOUNT: "Team is changing",
    PRIORITY: "Not a priority yet",
    UNSPECIFIED: "No reason given",
}

#: How long to wait, per reason. A budget objection resolves at the next
#: budget cycle; a contract objection resolves when the contract does, which
#: is usually longer; "we're busy this month" resolves fastest. Using one
#: interval for all of them is what makes re-engagement feel like spam.
INTERVAL_BY_KIND = {
    BUDGET: 90,
    CONTRACT: 180,
    TIMING: 60,
    PROJECT: 60,
    HEADCOUNT: 90,
    PRIORITY: 120,
    UNSPECIFIED: DEFAULT_INTERVAL_DAYS,
}

_SYSTEM = (
    "You read ONE reply from a prospect who has said 'not now' to cold "
    "outreach, and you extract what they actually said about coming back.\n"
    "Respond with ONLY a JSON object:\n"
    '{"reason_kind": "<kind>", "reason_text": "<their words, max 30 words>", '
    '"return_on": "YYYY-MM-DD or null", "confidence": <0..1>}\n'
    "<kind> is exactly one of: " + ", ".join(REASON_KINDS) + ".\n"
    "  budget     - no money allocated, spend frozen, next fiscal year\n"
    "  contract   - locked into another vendor or agreement\n"
    "  timing     - generally bad timing, busy season, 'not right now'\n"
    "  project    - mid-way through something else\n"
    "  headcount  - hiring, reorg, someone leaving or joining\n"
    "  priority   - it matters but other things matter more\n"
    "  unspecified- they said no for now and gave no reason\n"
    "`reason_text` QUOTES OR CLOSELY PARAPHRASES THEM. Never invent a reason "
    "they did not give -- 'unspecified' with an empty reason_text is the "
    "correct answer when they just said 'not now'.\n"
    "`return_on` is a real calendar date ONLY when they named a time you can "
    "resolve against TODAY'S DATE, which is given in the prompt. 'Q2', 'after "
    "the summer', 'in March' all resolve; 'later', 'sometime' do not -- use "
    "null."
)

_PROMPT = """TODAY: {today}

THE REPLY
From: {from_address}
Subject: {subject}

{body}

Extract what they said about coming back."""

#: The deterministic fallback, used when the model is unavailable. Crude on
#: purpose: it only fires on unambiguous phrasing, and anything it does not
#: recognise stays `unspecified` rather than being guessed at.
_RULES = [
    (BUDGET, re.compile(r"\b(budget|spend|funds?|fiscal|money|afford|cost centre|"
                        r"freeze|frozen)\b", re.I)),
    (CONTRACT, re.compile(r"\b(contract|locked in|agreement|renewal|under contract|"
                          r"tied in|existing (vendor|supplier|provider))\b", re.I)),
    (HEADCOUNT, re.compile(r"\b(hiring|reorg|restructur\w*|new (head|director|vp)|"
                           r"maternity|leaving|headcount)\b", re.I)),
    (PROJECT, re.compile(r"\b(mid[- ]?(way|project)|in the middle of|migration|"
                         r"rollout|implementation|go[- ]live)\b", re.I)),
    (PRIORITY, re.compile(r"\b(priorit\w*|bigger fish|further down|backlog|roadmap)\b",
                          re.I)),
    (TIMING, re.compile(r"\b(timing|busy season|swamped|too busy|not (a )?good time|"
                        r"revisit|circle back|check back|next (quarter|year|month))\b",
                        re.I)),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


def default_interval(db: Session) -> int:
    """The configured fallback interval, clamped to something sane.

    A 2-day "re-engagement" is a nag and a 5-year one is a rounding error, so
    an out-of-range setting is clamped rather than obeyed."""
    from app.services import system_settings  # noqa: PLC0415

    try:
        value = int(system_settings.get(db, "reengagement_memory_days"))
    except Exception:  # noqa: BLE001
        return DEFAULT_INTERVAL_DAYS
    return max(MIN_INTERVAL_DAYS, min(MAX_INTERVAL_DAYS, value))


def enabled(db: Session) -> bool:
    from app.services import system_settings  # noqa: PLC0415

    try:
        return bool(system_settings.get(db, "reengagement_memory_enabled"))
    except Exception:  # noqa: BLE001
        return True


def auto_send(db: Session) -> bool:
    from app.services import system_settings  # noqa: PLC0415

    try:
        return bool(system_settings.get(db, "reengagement_memory_auto_send"))
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------
# Reading the reply
# --------------------------------------------------------------------------


def _rule_kind(text: str) -> str:
    for kind, pattern in _RULES:
        if pattern.search(text or ""):
            return kind
    return UNSPECIFIED


def _clean_extraction(data: object, body: str, today: date) -> dict:
    data = data if isinstance(data, dict) else {}
    kind = str(data.get("reason_kind") or "").strip().lower()
    if kind not in REASON_KINDS:
        kind = _rule_kind(body)
    text = " ".join(str(data.get("reason_text") or "").split())[:500]
    return_on = None
    raw = data.get("return_on")
    if raw:
        try:
            parsed = date.fromisoformat(str(raw)[:10])
            # A date in the past is not a promise to come back, it is a
            # mis-resolution. Ignore it and fall back to the interval.
            return_on = parsed if parsed > today else None
        except (TypeError, ValueError):
            return_on = None
    return {"reason_kind": kind, "reason_text": text or None, "return_on": return_on}


def extract(db: Session, reply: InboundReply, today: date | None = None) -> dict:
    """What this prospect said about coming back.

    Never raises: a model outage degrades to the deterministic rules, which
    give a usable kind and no invented reason text. Losing the nuance is
    acceptable; losing the plan is not.
    """
    from app.services.anthropic_client import get_client  # noqa: PLC0415

    today = today or _now().date()
    body = reply.body or ""
    try:
        answer = get_client().complete_json(
            system=_SYSTEM,
            prompt=_PROMPT.format(today=today.isoformat(),
                                  from_address=reply.from_address or "(unknown)",
                                  subject=reply.subject or "(none)",
                                  body=body[:4000]),
            max_tokens=400,
        )
        return _clean_extraction(answer, body, today)
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        logger.warning("not-now extraction failed for reply %s (%s) — using rules",
                       reply.id, exc)
        return {"reason_kind": _rule_kind(body), "reason_text": None, "return_on": None}


def due_date_for(extraction: dict, *, fallback_days: int, today: date) -> tuple[date, int]:
    """(the day to come back, the interval it represents).

    A date the PROSPECT named always wins over any default: they know their
    own contract renewal and we do not.
    """
    stated = extraction.get("return_on")
    if isinstance(stated, date) and stated > today:
        return stated, (stated - today).days
    days = INTERVAL_BY_KIND.get(extraction.get("reason_kind"), fallback_days)
    # The admin's configured interval is the floor for "unspecified" only;
    # for a known kind the per-kind interval is the more informed number.
    if extraction.get("reason_kind") in (None, UNSPECIFIED):
        days = fallback_days
    return today + timedelta(days=days), days


# --------------------------------------------------------------------------
# Making the plan
# --------------------------------------------------------------------------


def _owner_id(db: Session, lead: Lead):
    strategy = db.get(Strategy, lead.strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    return product.user_id if product else None


def plan_for_reply(db: Session, reply: InboundReply,
                   now: datetime | None = None) -> ReengagementPlan | None:
    """Turn one `not_now` reply into a dated return visit.

    Returns the plan, or None when this reply is not a "not now", the feature
    is off, or a plan already exists for it (the UNIQUE makes that last case
    structural rather than a race).

    Never raises: this runs from the reply task, and a prospect who said "not
    now" must still be stored and routed exactly as before if this fails.
    """
    now = now or _now()
    try:
        if reply.intent_label != "not_now" or not enabled(db):
            return None
        if reply.lead_id is None:
            return None
        existing = db.execute(select(ReengagementPlan).where(
            ReengagementPlan.source_reply_id == reply.id)).scalar_one_or_none()
        if existing is not None:
            return existing

        lead = db.get(Lead, reply.lead_id)
        if lead is None:
            return None

        today = now.astimezone(timezone.utc).date()
        extraction = extract(db, reply, today=today)
        due_on, interval = due_date_for(extraction, fallback_days=default_interval(db),
                                        today=today)

        plan = ReengagementPlan(
            lead_id=lead.id,
            user_id=_owner_id(db, lead),
            strategy_id=lead.strategy_id,
            source_reply_id=reply.id,
            reason_kind=extraction["reason_kind"],
            reason_text=extraction["reason_text"],
            stated_return_on=extraction["return_on"],
            due_at=datetime.combine(due_on, datetime.min.time(), tzinfo=timezone.utc),
            interval_days=interval,
            status=SCHEDULED,
        )
        db.add(plan)
        try:
            db.commit()
        except IntegrityError:
            # Another pass got there first. Structural idempotency, not a race
            # we have to reason about.
            db.rollback()
            return db.execute(select(ReengagementPlan).where(
                ReengagementPlan.source_reply_id == reply.id)).scalar_one_or_none()

        _mirror_next_action(db, lead, plan)
        logger.info("re-engagement memory: lead %s scheduled for %s (%s)",
                    lead.id, due_on.isoformat(), plan.reason_kind)
        return plan
    except Exception as exc:  # noqa: BLE001 -- see the docstring
        logger.exception("could not plan re-engagement for reply %s: %s", reply.id, exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def _mirror_next_action(db: Session, lead: Lead, plan: ReengagementPlan) -> None:
    """Put the date on the CRM row too, so the existing follow-up machinery,
    the lead list and the kanban all show it without knowing this feature
    exists. Never raises."""
    try:
        from app.services import crm_service  # noqa: PLC0415

        meta = crm_service.get_or_create_meta(db, lead)
        if meta.next_action_at is None or _aware(meta.next_action_at) > plan.due_at:
            meta.next_action_at = plan.due_at
            db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("could not mirror the re-engagement date onto lead %s", lead.id)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------
# Coming back
# --------------------------------------------------------------------------


def still_appropriate(db: Session, plan: ReengagementPlan) -> str | None:
    """A reason NOT to come back, or None.

    Checked when the plan comes due, never when it was made: 90 days is long
    enough for the prospect to have unsubscribed, bounced, been suppressed, or
    replied with something better.
    """
    lead = db.get(Lead, plan.lead_id)
    if lead is None:
        return "the prospect record is gone"
    if lead.status in (LeadStatus.DROPPED, LeadStatus.DISQUALIFIED,
                       LeadStatus.CLOSED_LOST, LeadStatus.CLOSED_WON):
        return f"the prospect is now {lead.status.value}"
    if lead.status in (LeadStatus.MEETING_BOOKED, LeadStatus.OPPORTUNITY,
                       LeadStatus.PROPOSAL_SENT):
        return f"the prospect moved on to {lead.status.value} without this"
    if lead.kill_signal:
        return f"kill signal: {lead.kill_signal}"
    suppressed = db.execute(select(SuppressionEntry).where(
        SuppressionEntry.email == lead.email)).scalar_one_or_none() if lead.email else None
    if suppressed is not None:
        return f"suppressed ({suppressed.reason})"
    return None


def due_plans(db: Session, now: datetime | None = None,
              limit: int = 200) -> list[ReengagementPlan]:
    now = now or _now()
    return list(db.execute(
        select(ReengagementPlan)
        .where(ReengagementPlan.status == SCHEDULED, ReengagementPlan.due_at <= now)
        .order_by(ReengagementPlan.due_at)
        .limit(limit)
    ).scalars())


def cancel(db: Session, plan: ReengagementPlan, reason: str,
           now: datetime | None = None) -> ReengagementPlan:
    plan.status = CANCELLED
    plan.cancelled_reason = reason[:200]
    plan.completed_at = now or _now()
    db.commit()
    return plan


def reschedule(db: Session, plan: ReengagementPlan, new_due: datetime,
               now: datetime | None = None) -> ReengagementPlan:
    """Move the date. A person who knows the prospect knows better than the
    interval table, so this is always available -- including on a plan the
    sweep has already marked `due`."""
    plan.due_at = _aware(new_due)
    plan.status = SCHEDULED
    plan.interval_days = max(0, (plan.due_at - (now or _now())).days)
    db.commit()
    lead = db.get(Lead, plan.lead_id)
    if lead is not None:
        _mirror_next_action(db, lead, plan)
    return plan


def brief_for(plan: ReengagementPlan, lead: Lead) -> str:
    """The step brief for the return message.

    It QUOTES the prospect. The whole value of a 90-day memory is being able
    to open with "you said you were mid-contract until March" instead of
    "just circling back" -- the second is indistinguishable from every other
    unwanted follow-up they get.
    """
    who = lead.full_name or "there"
    when = plan.stated_return_on.isoformat() if plan.stated_return_on else "around now"
    quoted = (f'They said: "{plan.reason_text}".' if plan.reason_text
              else "They gave no reason beyond bad timing.")
    return (
        f"RE-ENGAGEMENT AFTER A 'NOT NOW'. {who} asked us to come back {when}. "
        f"{quoted} Open by referring to THAT, in their words, and acknowledging "
        f"the gap since. Do not pretend this is a first contact and do not "
        f"repeat the original pitch. One short paragraph, one question: has "
        f"what they described changed? Reason on file: "
        f"{REASON_LABELS.get(plan.reason_kind or UNSPECIFIED)}."
    )


def _last_message(db: Session, lead: Lead) -> Message | None:
    return db.execute(
        select(Message)
        .where(Message.lead_id == lead.id, Message.status == MessageStatus.SENT)
        .order_by(Message.step_no.desc())
    ).scalars().first()


def schedule_touch(db: Session, plan: ReengagementPlan,
                   now: datetime | None = None) -> Message | None:
    """Create the actual return message, SCHEDULED for the ordinary send path.

    Deliberately an ordinary Message: suppression, compliance, the send window,
    mailbox health and the human review queue all apply to it exactly as they
    apply to a step. This feature decides WHEN to knock; it does not decide
    that knocking is allowed.

    Returns None when there is nothing to send from (no previous message, so
    no channel and no sequence to hang it on) -- the plan still becomes `due`
    and the user is still told.
    """
    now = now or _now()
    lead = db.get(Lead, plan.lead_id)
    if lead is None:
        return None
    last = _last_message(db, lead)
    if last is None:
        return None
    enrollment = db.execute(select(SequenceEnrollment).where(
        SequenceEnrollment.sequence_id == last.sequence_id,
        SequenceEnrollment.lead_id == lead.id)).scalar_one_or_none()

    message = Message(
        sequence_id=last.sequence_id,
        lead_id=lead.id,
        channel=last.channel,
        step_no=last.step_no + 1,
        template=brief_for(plan, lead),
        variant=last.variant,
        origin=ORIGIN,
        status=MessageStatus.SCHEDULED,
        scheduled_at=now,
    )
    db.add(message)
    db.flush()
    plan.message_id = message.id
    db.commit()
    if enrollment is not None:
        logger.info("re-engagement memory touch scheduled for lead %s on enrollment %s",
                    lead.id, enrollment.id)
    return message


def run_due(db: Session, now: datetime | None = None, limit: int = 200) -> dict:
    """The sweep. Marks due plans, skips the ones that stopped being
    appropriate, and (when enabled) schedules the touch.

    One plan failing never stops the others.
    """
    now = now or _now()
    sending = auto_send(db)
    counts = {"checked": 0, "cancelled": 0, "due": 0, "scheduled": 0, "failed": 0}
    for plan in due_plans(db, now=now, limit=limit):
        counts["checked"] += 1
        try:
            blocked = still_appropriate(db, plan)
            if blocked:
                cancel(db, plan, blocked, now=now)
                counts["cancelled"] += 1
                continue
            plan.status = DUE
            db.commit()
            counts["due"] += 1
            if sending and schedule_touch(db, plan, now=now) is not None:
                plan.status = SENT
                plan.completed_at = now
                plan.outcome = "message scheduled"
                db.commit()
                counts["scheduled"] += 1
            _notify_due(db, plan)
        except Exception:  # noqa: BLE001
            counts["failed"] += 1
            logger.exception("re-engagement plan %s failed", plan.id)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
    return counts


def _notify_due(db: Session, plan: ReengagementPlan) -> None:
    """Never raises: a notification failure must not undo a due plan."""
    try:
        from app.workers import notification_tasks  # noqa: PLC0415

        if plan.user_id is None:
            return
        lead = db.get(Lead, plan.lead_id)
        who = (lead.full_name or lead.email or "a prospect") if lead else "a prospect"
        notification_tasks.enqueue_event(
            plan.user_id, "reengagement_due",
            title=f"Time to go back to {who}",
            body=(plan.reason_text or REASON_LABELS.get(plan.reason_kind or UNSPECIFIED)),
            deep_link=f"/leads/detail?id={plan.lead_id}",
            data={"plan_id": str(plan.id), "lead_id": str(plan.lead_id)},
            webhook_payload={"plan_id": str(plan.id), "lead_id": str(plan.lead_id),
                             "reason_kind": plan.reason_kind,
                             "status": plan.status})
    except Exception:  # noqa: BLE001
        logger.exception("could not notify re-engagement plan %s", plan.id)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def plan_out(db: Session, plan: ReengagementPlan) -> dict:
    lead = db.get(Lead, plan.lead_id)
    return {
        "id": str(plan.id),
        "lead": ({"id": str(lead.id), "full_name": lead.full_name,
                  "company": lead.company, "email": lead.email,
                  "status": lead.status.value if lead.status else None} if lead else None),
        "reason_kind": plan.reason_kind,
        "reason_label": REASON_LABELS.get(plan.reason_kind or UNSPECIFIED),
        "reason_text": plan.reason_text,
        # True when the PROSPECT named the date. "They asked for March" and
        # "we guessed 90 days" are different promises, and the UI says which.
        "date_from_prospect": plan.stated_return_on is not None,
        "stated_return_on": (plan.stated_return_on.isoformat()
                             if plan.stated_return_on else None),
        "due_at": plan.due_at.isoformat() if plan.due_at else None,
        "interval_days": plan.interval_days,
        "status": plan.status,
        "message_id": str(plan.message_id) if plan.message_id else None,
        "outcome": plan.outcome,
        "cancelled_reason": plan.cancelled_reason,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


def list_plans(db: Session, user_id, *, status: str | None = SCHEDULED,
               limit: int = 100, offset: int = 0) -> dict:
    query = select(ReengagementPlan).where(ReengagementPlan.user_id == user_id)
    if status:
        query = query.where(ReengagementPlan.status == status)
    rows = list(db.execute(
        query.order_by(ReengagementPlan.due_at).offset(offset).limit(limit)).scalars())
    total = len(list(db.execute(
        select(ReengagementPlan.id).where(ReengagementPlan.user_id == user_id)
        .where(ReengagementPlan.status == status) if status
        else select(ReengagementPlan.id).where(
            ReengagementPlan.user_id == user_id)).all()))
    return {"total": total, "limit": limit, "offset": offset, "status": status,
            "items": [plan_out(db, plan) for plan in rows]}


def for_lead(db: Session, lead_id) -> list[dict]:
    rows = db.execute(
        select(ReengagementPlan)
        .where(ReengagementPlan.lead_id == lead_id)
        .order_by(ReengagementPlan.due_at.desc())).scalars()
    return [plan_out(db, plan) for plan in rows]
