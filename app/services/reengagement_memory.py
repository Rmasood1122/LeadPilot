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
`reengagement_memory_auto_send` is on (it is OFF by default -- an admin turns
it on in system settings), it also schedules a real message through the
ordinary send path -- so suppression, exclusions, compliance, mailbox health
and the human review queue all still apply. Nothing here bypasses a gate; it
only decides WHEN to knock.

THE ONE STOPPED-ENROLLMENT EXCEPTION. The touch is attached to the sequence
the prospect's reply stopped (that is the thread it continues). A stopped
enrollment cancels every message at send time, so the touch used to be
cancelled on the day it was due. send_message_impl now lets a touch of THIS
origin pass a stopped enrollment only when answers_the_stop() below ties the
stop to the reply the plan was made from (or an earlier reply of the same
lead) -- the same narrow rule Reply Copilot answers use. Every other gate
applies unchanged, and send_time_hold() adds this feature's own: the feature
or auto-send switched off since scheduling, the plan cancelled, the
prospect no longer appropriate (still_appropriate), or a newer reply from
the prospect -- each cancels the touch.

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

from app.services import prompt_safety

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

#: F10 Champion Tracker: a plan created because a champion (a past positive
#: replier or a customer) moved to a new company. NOT in REASON_KINDS on
#: purpose: REASON_KINDS is the vocabulary the "not now" extraction prompt
#: offers the model, and a reply can never be a job change detected by
#: enrichment. PLAN_LABELS is what every plan (either origin) is shown with.
JOB_CHANGE = "job_change"
PLAN_LABELS = {**REASON_LABELS, JOB_CHANGE: "Changed jobs"}

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

# Output contract (Phase 3 item 2). `confidence` is asked for but not read.
NOT_NOW_SCHEMA = {
    "type": "object",
    "properties": {
        "reason_kind": {"type": "string", "enum": list(REASON_KINDS)},
        "reason_text": {"type": "string"},
        "return_on": {"type": ["string", "null"]},
        "confidence": {"type": ["number", "string"]},
    },
    "required": ["reason_kind", "reason_text", "return_on"],
    "additionalProperties": False,
}

# F-AI-02: sender, subject and body are written by the prospect.
_PROMPT = """{notice}

TODAY: {today}

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
            prompt=_PROMPT.format(
                notice=prompt_safety.NOTICE,
                today=today.isoformat(),
                from_address=prompt_safety.inline(reply.from_address or "(unknown)"),
                subject=prompt_safety.inline(reply.subject or "(none)"),
                body=prompt_safety.block(body[:4000])),
            max_tokens=400,
            schema=NOT_NOW_SCHEMA,
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
        # Local business mode: no dated return visit (a model extraction and
        # a model-written touch) for a business's own customer.
        from app.services.local_business import is_customer  # noqa: PLC0415

        if is_customer(lead):
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
    # All three identifiers, the same check the send path makes
    # (lead_tasks.is_suppressed): an opt-out by phone or on LinkedIn must
    # cancel the plan too, not only an email unsubscribe. The email row's
    # reason is kept in the text when it is the email that matched.
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    if lead.email and is_suppressed(db, email=lead.email):
        entry = db.execute(select(SuppressionEntry).where(
            SuppressionEntry.email == lead.email.lower().strip()).limit(1)).scalars().first()
        return f"suppressed ({entry.reason if entry is not None else 'email'})"
    if lead.phone and is_suppressed(db, phone=lead.phone):
        return "suppressed (phone number)"
    if lead.linkedin_url and is_suppressed(db, linkedin=lead.linkedin_url):
        return "suppressed (LinkedIn profile)"
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


def pending_touch(db: Session, plan: ReengagementPlan) -> Message | None:
    """The plan's return message while it has NOT gone out yet and can still
    be stopped: scheduled, waiting in the review queue, or held by a send-time
    guard. Not SENDING (a worker is transmitting it now) and not sent."""
    from app.services import send_holds  # noqa: PLC0415

    if plan.message_id is None:
        return None
    message = db.get(Message, plan.message_id)
    if message is None:
        return None
    if message.status in (MessageStatus.SCHEDULED, MessageStatus.AWAITING_REVIEW):
        return message
    if message.status is MessageStatus.FAILED and (message.error or "").startswith(
            send_holds.HOLD_PREFIXES):
        return message
    return None


def can_cancel(db: Session, plan: ReengagementPlan) -> bool:
    """A plan can be cancelled while it is scheduled or due, and after the
    sweep scheduled its return message as long as that message has not gone
    out (pending_touch)."""
    if plan.status in (SCHEDULED, DUE):
        return True
    return plan.status == SENT and pending_touch(db, plan) is not None


def cancel(db: Session, plan: ReengagementPlan, reason: str,
           now: datetime | None = None) -> ReengagementPlan:
    """Cancel the plan, and its return message if it has not gone out yet
    (send_time_hold would also cancel it at send time; cancelling it here
    takes it off the queue and the review list now)."""
    touch = pending_touch(db, plan) if plan.status == SENT else None
    plan.status = CANCELLED
    plan.cancelled_reason = reason[:200]
    plan.completed_at = now or _now()
    if touch is not None:
        touch.status = MessageStatus.CANCELLED
        touch.error = f"re-engagement: plan cancelled ({reason})"[:1000]
        plan.outcome = "return message cancelled before sending"
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
    # The brief becomes the step template, which every renderer reads as OUR
    # instructions (message_personalization, the call script). The prospect's
    # name and their own words are outside text, so they arrive delimited;
    # each renderer's prompt carries prompt_safety.NOTICE.
    who = prompt_safety.inline(lead.full_name or "there")
    if plan.reason_kind == JOB_CHANGE:
        return _job_change_brief(lead, who)
    when = plan.stated_return_on.isoformat() if plan.stated_return_on else "around now"
    quoted = (f"They said: {prompt_safety.inline(plan.reason_text)}." if plan.reason_text
              else "They gave no reason beyond bad timing.")
    return (
        f"RE-ENGAGEMENT AFTER A 'NOT NOW'. {who} asked us to come back {when}. "
        f"{quoted} Open by referring to THAT, in their words, and acknowledging "
        f"the gap since. Do not pretend this is a first contact and do not "
        f"repeat the original pitch. One short paragraph, one question: has "
        f"what they described changed? Reason on file: "
        f"{REASON_LABELS.get(plan.reason_kind or UNSPECIFIED)}."
    )


def _job_change_brief(lead: Lead, who: str) -> str:
    """F10: the brief for a champion who moved. It states only what enrichment
    recorded (old and new company/title) and never claims the prospect SAID
    anything -- a job change is something we observed, not something they
    told us."""
    champion = (lead.enrichment_json or {}).get("champion") or {}
    # Each "title at company" phrase is enrichment text, delimited as one value.
    before = " at ".join(str(p) for p in (champion.get("from_title"),
                                          champion.get("from_company")) if p)
    before = prompt_safety.inline(before) if before else "their previous company"
    now_at = " at ".join(p for p in (lead.title, lead.company) if p)
    now_at = prompt_safety.inline(now_at) if now_at else "a new company"
    return (
        f"RE-ENGAGEMENT AFTER A JOB CHANGE. {who} worked with us before as "
        f"{before} and is now {now_at}. Acknowledge the move briefly and "
        f"congratulate them once. Refer to the earlier relationship only in "
        f"general terms; do not quote anything they said and do not claim "
        f"anything about their new company that is not in the stored data. "
        f"This is not a first contact and not a hard pitch: one short "
        f"paragraph, one question about whether the same problem exists in "
        f"the new role."
    )


def plan_for_job_change(db: Session, lead: Lead, *, owner_id,
                        now: datetime | None = None) -> ReengagementPlan:
    """F10: the re-engagement plan for a champion's NEW lead.

    Created already `due`, because the move itself is the trigger -- there is
    no date to wait for. Being `due` (not `scheduled`) also means the daily
    sweep never picks it up, so `reengagement_memory_auto_send` cannot turn
    it into a message on its own: the new lead has no sequence and no sent
    message, and nothing here creates either. A person decides.

    Idempotent per lead: an existing job-change plan for the lead is returned.
    Commits. The CRM next-action mirror and the notification never raise.
    """
    now = now or _now()
    existing = db.execute(select(ReengagementPlan).where(
        ReengagementPlan.lead_id == lead.id,
        ReengagementPlan.reason_kind == JOB_CHANGE)).scalars().first()
    if existing is not None:
        return existing
    plan = ReengagementPlan(
        lead_id=lead.id,
        user_id=owner_id,
        strategy_id=lead.strategy_id,
        source_reply_id=None,
        reason_kind=JOB_CHANGE,
        # The prospect said nothing: reason_text is THEIR words and stays empty.
        reason_text=None,
        stated_return_on=None,
        due_at=now,
        interval_days=0,
        status=DUE,
    )
    db.add(plan)
    db.commit()
    _mirror_next_action(db, lead, plan)
    _notify_due(db, plan)
    return plan


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


# --------------------------------------------------------------------------
# Send time (called by outreach_tasks.send_message_impl, ON TOP of every gate)
# --------------------------------------------------------------------------

#: Routing classes whose stop is never passed: those people asked to stop or
#: their address is gone (both also suppress, so this is belt and braces).
_NEVER_PASS = frozenset({"unsubscribe_request", "bounce"})


def _stored_at(reply: InboundReply) -> datetime | None:
    return _aware(reply.created_at or reply.received_at)


def plan_for_message(db: Session, message: Message) -> ReengagementPlan | None:
    return db.execute(select(ReengagementPlan).where(
        ReengagementPlan.message_id == message.id)).scalars().first()


def answers_the_stop(db: Session, message: Message,
                     enrollment: SequenceEnrollment | None) -> bool:
    """May this re-engagement touch pass a STOPPED enrollment?

    Only a touch of this origin, with its plan, whose enrollment was stopped
    by a reply: stop_reason is "replied_<class>" of the plan's source reply or
    of an earlier reply of the same lead, stored no later than the stop. An
    enrollment that was stopped for any OTHER reason first (an unsubscribe,
    a bounce, suppression, a removed lead, a meeting outcome, a kill
    signal...) keeps the touch cancelled.

    WHAT THIS DOES NOT SEE. stop_reason records the FIRST stop only:
    stop_enrollment is never called on an enrollment that is already
    STOPPED, so an unsubscribe, bounce, removal or meeting outcome that comes
    AFTER the "not now" reply does not change it, and this function still
    returns True. Those later events are caught by the other send-time checks
    instead: the suppression gate (an unsubscribe, a bounce, a STOP reply and
    an erasure all suppress), the dropped-lead gate, the F05 / F10 gates,
    and send_time_hold below -- still_appropriate (lead status dropped,
    disqualified, closed, meeting booked, opportunity, proposal sent; a kill
    signal on the lead) and the newer-reply check."""
    from app.db.models import EnrollmentStatus  # noqa: PLC0415

    if (message.origin != ORIGIN or enrollment is None
            or enrollment.status is not EnrollmentStatus.STOPPED
            or not (enrollment.stop_reason or "").startswith("replied_")
            or enrollment.stopped_at is None):
        return False
    plan = plan_for_message(db, message)
    source = db.get(InboundReply, plan.source_reply_id) if plan and plan.source_reply_id else None
    if source is None or source.lead_id != message.lead_id:
        return False
    stopped = _aware(enrollment.stopped_at)
    source_at = _stored_at(source)
    for reply in db.execute(select(InboundReply).where(
            InboundReply.lead_id == message.lead_id)).scalars():
        cls = (reply.classification or "").lower()
        at = _stored_at(reply)
        if (cls and cls not in _NEVER_PASS and at is not None and source_at is not None
                and at <= source_at and at <= stopped
                and f"replied_{cls}" == enrollment.stop_reason):
            return True
    return False


def send_time_hold(db: Session, message: Message, lead: Lead,
                   now: datetime | None = None) -> str | None:
    """Extra send-time checks for a touch of this origin. Returns a status
    that ends the send (the message is CANCELLED, the reason on it) or None.
    """
    now = now or _now()
    plan = plan_for_message(db, message)
    reason = status = None
    if not enabled(db) or not auto_send(db):
        status, reason = "cancelled_reengagement_off", "re-engagement auto-send switched off"
    elif plan is None or plan.status == CANCELLED:
        status, reason = "cancelled_plan_cancelled", "re-engagement plan cancelled"
    else:
        blocked = still_appropriate(db, plan)
        if blocked:
            status, reason = "cancelled_reengagement_inappropriate", blocked
        elif plan.source_reply_id is not None:
            source = db.get(InboundReply, plan.source_reply_id)
            source_at = _stored_at(source) if source is not None else None
            newer = source_at is not None and any(
                (_stored_at(r) or source_at) > source_at
                and (r.classification or "") != "automated_response"
                for r in db.execute(select(InboundReply).where(
                    InboundReply.lead_id == lead.id,
                    InboundReply.id != source.id)).scalars())
            if newer:
                status, reason = ("cancelled_prospect_wrote_again",
                                  "the prospect wrote again after the 'not now' reply")
    if status is None:
        return None
    message.status = MessageStatus.CANCELLED
    message.error = f"re-engagement: {reason}"[:1000]
    db.commit()
    return status


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
            body=(plan.reason_text or PLAN_LABELS.get(plan.reason_kind or UNSPECIFIED)),
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
        "reason_label": PLAN_LABELS.get(plan.reason_kind or UNSPECIFIED),
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
        # The return message is scheduled but has not gone out: it can still
        # be cancelled (POST /reengagement/plans/{id}/cancel).
        "touch_pending": plan.status == SENT and pending_touch(db, plan) is not None,
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
