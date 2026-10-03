"""Sequence completion guarantee and its metric (Part 1, Feature 3).

THE PROMISE. A sequence stops early ONLY for a reason a person would recognise
as a decision: the prospect replied and the reply was routed, they
unsubscribed, the address bounced, they booked, compliance suppressed them, or
someone closed them in the CRM. Everything else means a prospect quietly
stopped being contacted halfway through a campaign that was still running --
which is the failure this feature exists to make impossible to hide.

HOW THE GUARANTEE IS ENFORCED
  1. Every stop already goes through sequence_engine.stop_enrollment. That
     function now also records WHEN it stopped and, through categorize()
     below, WHAT KIND of stop it was.
  2. categorize() maps the free-text reason onto a fixed vocabulary. An
     unrecognised reason becomes "other" AND is logged at warning level, so a
     new call site that invents a reason shows up in the logs and in the
     metric's `unauthorised` bucket instead of vanishing.
  3. AUTHORISED holds the categories that are legitimate early stops. The
     rest -- an automated kill signal, an enrollment where every step was
     skipped, an unrecognised reason -- are reported separately as
     `dropped_unauthorised`, because "the system decided" is not the same as
     "a person decided".

THE METRIC. Completion rate = enrollments that received every planned step /
enrollments that have finished one way or another. Still-running enrollments
are in neither numerator nor denominator: a campaign on step 2 of 5 has not
failed to complete, it simply has not finished.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    EnrollmentStatus,
    Lead,
    Sequence,
    SequenceEnrollment,
)

logger = logging.getLogger(__name__)

# --- The vocabulary -------------------------------------------------------
REPLIED = "replied"
UNSUBSCRIBED = "unsubscribed"
BOUNCED = "bounced"
MEETING_BOOKED = "meeting_booked"
SUPPRESSED = "suppressed"
OPTED_OUT = "opted_out"
CRM_CLOSED = "crm_closed"
CALL_OUTCOME = "call_outcome"
SYSTEM_KILL = "system_kill"
ALL_STEPS_SKIPPED = "all_steps_skipped"
OTHER = "other"

CATEGORIES = (REPLIED, UNSUBSCRIBED, BOUNCED, MEETING_BOOKED, SUPPRESSED,
              OPTED_OUT, CRM_CLOSED, CALL_OUTCOME, SYSTEM_KILL,
              ALL_STEPS_SKIPPED, OTHER)

#: Early stops a person would recognise as a decision. Everything outside this
#: set is reported as an unauthorised drop, however sensible it looked at the
#: time -- including the automated kill signal, which is a product decision
#: worth seeing the volume of.
AUTHORISED = frozenset({REPLIED, UNSUBSCRIBED, BOUNCED, MEETING_BOOKED,
                        SUPPRESSED, OPTED_OUT, CRM_CLOSED, CALL_OUTCOME})

#: Human-readable labels for the breakdown, so the UI never renders a slug.
LABELS = {
    REPLIED: "Prospect replied",
    UNSUBSCRIBED: "Unsubscribed",
    BOUNCED: "Bounced",
    MEETING_BOOKED: "Meeting booked",
    SUPPRESSED: "Suppressed (compliance)",
    OPTED_OUT: "Opted out",
    CRM_CLOSED: "Closed in the CRM",
    CALL_OUTCOME: "Ended on a call outcome",
    SYSTEM_KILL: "Stopped by an automated kill signal",
    ALL_STEPS_SKIPPED: "Every step was skipped",
    OTHER: "Unrecognised reason",
}

#: reason-prefix -> category. Ordered longest-first at match time so
#: "replied_unsubscribe_request" cannot be read as a plain reply.
_PREFIXES: tuple[tuple[str, str], ...] = (
    ("replied_unsubscribe_request", UNSUBSCRIBED),
    ("replied_bounce", BOUNCED),
    ("replied", REPLIED),
    ("unsubscribed", UNSUBSCRIBED),
    ("bounced", BOUNCED),
    ("meeting_booked", MEETING_BOOKED),
    ("suppressed", SUPPRESSED),
    ("whatsapp_optout", OPTED_OUT),
    ("opted_out", OPTED_OUT),
    ("crm_", CRM_CLOSED),
    ("call_", CALL_OUTCOME),
    ("kill_signal", SYSTEM_KILL),
    ("completed_all_skipped", ALL_STEPS_SKIPPED),
)


def categorize(reason: str | None) -> str:
    """Map a free-text stop reason onto the fixed vocabulary.

    An unrecognised reason is `other` AND is logged: a new call site that
    invents a reason must show up somewhere a person will see it, rather than
    quietly widening the "unauthorised drop" bucket with no explanation.
    """
    text = (reason or "").strip().lower()
    if not text:
        logger.warning("sequence stop with no reason at all -- categorised as %s", OTHER)
        return OTHER
    for prefix, category in sorted(_PREFIXES, key=lambda p: -len(p[0])):
        if text.startswith(prefix):
            return category
    logger.warning("unrecognised sequence stop reason %r -- categorised as %s. "
                   "Add it to sequence_completion._PREFIXES.", reason, OTHER)
    return OTHER


def is_authorised(category: str | None) -> bool:
    """True when this stop was a decision, not a silent drop."""
    return category in AUTHORISED


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Per-enrollment state
# --------------------------------------------------------------------------


def completed_every_step(enrollment: SequenceEnrollment) -> bool | None:
    """Did this prospect receive every step they were enrolled into?

    None means "cannot be answered": the enrollment predates this feature and
    carries no `planned_steps` snapshot. Reporting that as False would invent
    a failure out of missing data.
    """
    if enrollment.planned_steps is None:
        return None
    return (enrollment.steps_sent or 0) >= enrollment.planned_steps


def outcome_of(enrollment: SequenceEnrollment) -> str:
    """running | completed | dropped | unknown -- one word per enrollment."""
    if enrollment.status in (EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED):
        return "running"
    full = completed_every_step(enrollment)
    if full is None:
        return "unknown"
    return "completed" if full else "dropped"


def enrollment_out(enrollment: SequenceEnrollment) -> dict:
    """The per-enrollment block the API returns."""
    category = enrollment.stop_category
    return {
        "enrollment_id": str(enrollment.id),
        "lead_id": str(enrollment.lead_id),
        "status": enrollment.status.value if enrollment.status else None,
        "planned_steps": enrollment.planned_steps,
        "steps_sent": enrollment.steps_sent or 0,
        "outcome": outcome_of(enrollment),
        "stop_reason": enrollment.stop_reason,
        "stop_category": category,
        "stop_label": LABELS.get(category) if category else None,
        "authorised": is_authorised(category) if category else None,
        "completed_at": (enrollment.completed_at.isoformat()
                         if enrollment.completed_at else None),
        "stopped_at": enrollment.stopped_at.isoformat() if enrollment.stopped_at else None,
    }


# --------------------------------------------------------------------------
# The metric
# --------------------------------------------------------------------------


def _rate(numerator: int, denominator: int) -> float | None:
    """None, never 0.0, on an empty denominator -- a campaign where nothing
    has finished has no completion rate yet."""
    return round(numerator / denominator, 4) if denominator else None


def _metrics(enrollments: list[SequenceEnrollment]) -> dict:
    counts = {"running": 0, "completed": 0, "dropped": 0, "unknown": 0}
    breakdown = {name: 0 for name in CATEGORIES}
    unauthorised = 0
    for enrollment in enrollments:
        counts[outcome_of(enrollment)] += 1
        category = enrollment.stop_category
        if category:
            breakdown[category] = breakdown.get(category, 0) + 1
            if not is_authorised(category):
                unauthorised += 1

    finished = counts["completed"] + counts["dropped"]
    return {
        "enrolled": len(enrollments),
        "running": counts["running"],
        "completed": counts["completed"],
        "dropped": counts["dropped"],
        # Enrollments from before this feature: no planned_steps snapshot, so
        # completion is unanswerable. Reported, never counted as a failure.
        "unknown": counts["unknown"],
        "finished": finished,
        "completion_rate": _rate(counts["completed"], finished),
        # The number that matters for the guarantee: prospects who stopped
        # being contacted without a decision behind it.
        "dropped_unauthorised": unauthorised,
        "reasons": [
            {"category": name, "label": LABELS[name], "count": breakdown[name],
             "authorised": name in AUTHORISED}
            for name in CATEGORIES if breakdown.get(name)
        ],
    }


def sequence_metrics(db: Session, sequence_id) -> dict:
    enrollments = db.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.sequence_id == sequence_id)
    ).scalars().all()
    return {"sequence_id": str(sequence_id), **_metrics(list(enrollments))}


def strategy_metrics(db: Session, strategy_id) -> dict:
    """Completion across every sequence in a campaign, plus a per-sequence
    breakdown so a single bad sequence is visible rather than averaged away."""
    enrollments = db.execute(
        select(SequenceEnrollment)
        .join(Sequence, Sequence.id == SequenceEnrollment.sequence_id)
        .where(Sequence.strategy_id == strategy_id)
    ).scalars().all()
    sequences = db.execute(
        select(Sequence).where(Sequence.strategy_id == strategy_id)
    ).scalars().all()

    by_sequence = []
    for sequence in sequences:
        rows = [e for e in enrollments if e.sequence_id == sequence.id]
        by_sequence.append({"sequence_id": str(sequence.id), "name": sequence.name,
                            **_metrics(rows)})
    return {"strategy_id": str(strategy_id), **_metrics(list(enrollments)),
            "by_sequence": by_sequence}


def dropped_enrollments(db: Session, strategy_id, *, unauthorised_only: bool = False,
                        limit: int = 100) -> list[dict]:
    """The prospects who stopped early, newest first -- the work list behind
    the number. `unauthorised_only` is the one a person should act on."""
    rows = db.execute(
        select(SequenceEnrollment, Lead)
        .join(Sequence, Sequence.id == SequenceEnrollment.sequence_id)
        .join(Lead, Lead.id == SequenceEnrollment.lead_id)
        .where(Sequence.strategy_id == strategy_id,
               SequenceEnrollment.status == EnrollmentStatus.STOPPED)
        .order_by(SequenceEnrollment.stopped_at.desc().nullslast())
        .limit(limit)
    ).all()
    out = []
    for enrollment, lead in rows:
        if unauthorised_only and is_authorised(enrollment.stop_category):
            continue
        out.append({**enrollment_out(enrollment),
                    "lead": {"id": str(lead.id), "full_name": lead.full_name,
                             "company": lead.company, "email": lead.email}})
    return out
