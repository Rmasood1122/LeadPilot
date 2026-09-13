"""Live conversion probability and kill-signal detection (Feature A5).

A lead's chance of booking is not fixed at sourcing. Every unanswered send
lowers it, an open or a click raises it (less the longer ago it was), a
genuine reply moves it a lot, and some events end it outright. This module
keeps that number live and ACTS on it, so a campaign stops spending sends --
and sender reputation -- on leads that have gone cold.

THE ESTIMATE (compute) is a small, explainable Bayesian update in odds form:
  prior      the lead's AI booking likelihood (Feature Group 1), else the
             `conversion_default_prior` setting
  replies    genuine interested x6, question x3, objection x1.5
  sends      each send since the last genuine reply multiplies the odds by the
             channel's no-reply likelihood ratio (email 0.85, LinkedIn 0.8,
             WhatsApp 0.75, phone 0.8)
  opens      x(1 + 0.5w), clicks x(1 + 1.5w), w = exponential decay by age
             (score_decay.engagement_weight, 14-day half-life)
  inactivity after a 7-day grace, odds x(0.5 + 0.5w) with the configured
             half-life -- time alone can halve the odds, never zero them
Every factor is returned, so the number on the lead page can be explained.

KILL SIGNALS end the lead regardless of probability: a bounce, an unsubscribe
or opt-out, a genuine "not interested". A booked or won meeting is the opposite
terminal state ("won").

RECLASSIFICATION (reclassify)
  archived  kill signal, or p < archive threshold   -> enrollments STOPPED
  cooling   p < cooling threshold                    -> enrollments PAUSED for
                                                       conversion_cooling_pause_days
  active    back above 1.5x the cooling threshold (hysteresis, so a lead does
            not flap between states on every open)
Probability alone never cools or archives a lead before
`conversion_min_unanswered_sends` unanswered sends -- a lead with a low AI
score still gets a fair first few touches. Archive is sticky: only a person
reactivating the lead reverses it. The lead is tagged "cooling"/"archived" in
the CRM, so the state is visible and filterable where people work.

WHERE IT RUNS: before every send (send_gate, called by send_message_impl) and
hourly over every lead with a live enrollment (app/workers/conversion_tasks.py).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CrmLeadTag,
    CrmTag,
    EnrollmentStatus,
    InboundReply,
    Lead,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    SequenceEnrollment,
)

logger = logging.getLogger(__name__)

NO_REPLY_LR = {"email": 0.85, "linkedin": 0.8, "whatsapp": 0.75, "phone": 0.8}
REPLY_LR = {"interested": 6.0, "question": 3.0, "objection": 1.5}
ENGAGEMENT_HALF_LIFE_DAYS = 14
INACTIVITY_GRACE_DAYS = 7
HARD_KILLS = ("bounced", "unsubscribed", "not_interested")
_AUTOMATED_KINDS = ("out_of_office", "auto_responder", "bot", "bounce")
_AUTOMATED_CLASSES = ("automated_response", "out_of_office", "bounce")


@dataclass
class Estimate:
    probability: float
    band: str                 # won | hot | warm | cold | cooling
    kill_signal: str | None
    unanswered_sends: int
    factors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"probability": self.probability, "band": self.band,
                "kill_signal": self.kill_signal, "unanswered_sends": self.unanswered_sends,
                "factors": list(self.factors)}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _setting(session: Session, key: str):
    from app.services import system_settings  # noqa: PLC0415

    return system_settings.get(session, key)


def _event(value) -> str:
    return str(getattr(value, "value", value) or "")


def compute(session: Session, lead: Lead, now: datetime | None = None) -> Estimate:
    from app.services.score_decay import engagement_weight  # noqa: PLC0415

    now = now or _now()
    outcomes = session.execute(
        select(Outcome.event, Outcome.channel, Outcome.ts).where(Outcome.lead_id == lead.id)
    ).all()
    events = {_event(e) for e, _, _ in outcomes}
    if events & {"booked", "won"}:
        return Estimate(1.0 if "won" in events else 0.95, "won", None, 0,
                        [{"factor": "meeting_booked", "effect": "terminal"}])
    if events & {"unsubscribed", "opted_out"}:
        return Estimate(0.0, "cooling", "unsubscribed", 0,
                        [{"factor": "unsubscribed", "effect": "kill"}])
    if "bounced" in events:
        return Estimate(0.0, "cooling", "bounced", 0, [{"factor": "bounced", "effect": "kill"}])

    replies = session.execute(
        select(InboundReply.classification, InboundReply.authenticity_kind,
               InboundReply.received_at, InboundReply.created_at)
        .where(InboundReply.lead_id == lead.id)
    ).all()
    genuine = sorted(
        ((_aware(received or created), cls) for cls, kind, received, created in replies
         if cls not in _AUTOMATED_CLASSES and kind not in _AUTOMATED_KINDS),
        key=lambda pair: pair[0] or now)
    if genuine and genuine[-1][1] == "unsubscribe_request":
        return Estimate(0.0, "cooling", "unsubscribed", 0,
                        [{"factor": "asked_to_stop", "effect": "kill"}])
    if genuine and genuine[-1][1] == "not_interested":
        return Estimate(0.01, "cooling", "not_interested", 0,
                        [{"factor": "replied_not_interested", "effect": "kill"}])

    factors: list[dict] = []
    if lead.ai_booking_likelihood is not None:
        prior = min(max(lead.ai_booking_likelihood / 100.0, 0.01), 0.9)
        factors.append({"factor": "ai_booking_likelihood", "value": round(prior, 3)})
    else:
        prior = float(_setting(session, "conversion_default_prior"))
        factors.append({"factor": "default_prior", "value": round(prior, 3)})
    odds = prior / (1.0 - prior)

    last_reply_at = genuine[-1][0] if genuine else None
    for at, cls in genuine:
        lr = REPLY_LR.get(cls or "")
        if lr:
            odds *= lr
            factors.append({"factor": f"reply_{cls}", "multiplier": lr})

    unanswered = 0
    per_channel: dict[str, int] = {}
    for event, channel, ts in outcomes:
        ts = _aware(ts)
        if _event(event) != "sent" or (last_reply_at and ts and ts <= last_reply_at):
            continue
        per_channel[channel or "email"] = per_channel.get(channel or "email", 0) + 1
    for channel, count in per_channel.items():
        lr = NO_REPLY_LR.get(channel, 0.85) ** count
        odds *= lr
        unanswered += count
        factors.append({"factor": f"unanswered_{channel}", "count": count,
                        "multiplier": round(lr, 4)})

    latest_open = max((_aware(ts) for e, _, ts in outcomes if _event(e) == "opened" and ts),
                      default=None)
    latest_click = max((_aware(ts) for e, _, ts in outcomes if _event(e) == "clicked" and ts),
                       default=None)
    for label, at, bump in (("opened", latest_open, 0.5), ("clicked", latest_click, 1.5)):
        if at is None:
            continue
        w = engagement_weight(max((now - at).total_seconds() / 86400.0, 0.0),
                              ENGAGEMENT_HALF_LIFE_DAYS)
        odds *= 1.0 + bump * w
        factors.append({"factor": label, "multiplier": round(1.0 + bump * w, 4)})

    first_send = min((_aware(ts) for e, _, ts in outcomes if _event(e) == "sent" and ts),
                     default=None)
    anchor = max([t for t in (last_reply_at, latest_open, latest_click) if t is not None],
                 default=first_send)
    if anchor is not None:
        idle_days = (now - anchor).total_seconds() / 86400.0 - INACTIVITY_GRACE_DAYS
        if idle_days > 0:
            w = engagement_weight(idle_days, int(_setting(session,
                                                          "conversion_inactivity_half_life_days")))
            multiplier = 0.5 + 0.5 * w
            odds *= multiplier
            factors.append({"factor": "inactivity", "idle_days": round(idle_days, 1),
                            "multiplier": round(multiplier, 4)})

    probability = round(min(max(odds / (1.0 + odds), 0.001), 0.99), 4)
    return Estimate(probability, _band(session, probability), None, unanswered, factors)


def _band(session: Session, p: float) -> str:
    if p < float(_setting(session, "conversion_cooling_threshold")):
        return "cooling"
    if p >= 0.4:
        return "hot"
    return "warm" if p >= 0.15 else "cold"


# --------------------------------------------------------------------------
# Acting on it
# --------------------------------------------------------------------------


def _set_tag(session: Session, user_id, lead_id, name: str, color: str, present: bool) -> None:
    if user_id is None:
        return
    tag = session.execute(select(CrmTag).where(CrmTag.user_id == user_id,
                                               CrmTag.name == name)).scalar_one_or_none()
    if tag is None:
        if not present:
            return
        tag = CrmTag(user_id=user_id, name=name, color_token=color)
        session.add(tag)
        session.flush()
    link = session.execute(select(CrmLeadTag).where(CrmLeadTag.lead_id == lead_id,
                                                    CrmLeadTag.tag_id == tag.id)).scalar_one_or_none()
    if present and link is None:
        session.add(CrmLeadTag(lead_id=lead_id, tag_id=tag.id))
    elif not present and link is not None:
        session.delete(link)


def _enrollments(session: Session, lead_id) -> list[SequenceEnrollment]:
    return list(session.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.lead_id == lead_id)).scalars())


def reclassify(session: Session, lead: Lead, estimate: Estimate,
               now: datetime | None = None) -> str:
    """Store the estimate and move the lead's state, pausing or stopping its
    sequences as the state requires. Commits. Returns the new state."""
    from app.services import notifications  # noqa: PLC0415
    from app.services import sequence_engine as engine  # noqa: PLC0415

    now = now or _now()
    cooling = float(_setting(session, "conversion_cooling_threshold"))
    archive = float(_setting(session, "conversion_archive_threshold"))
    judged = estimate.unanswered_sends >= int(_setting(session, "conversion_min_unanswered_sends"))
    previous = lead.engagement_state or "active"

    if estimate.band == "won":
        state = "won"
    elif estimate.kill_signal or previous == "archived" or (judged and estimate.probability < archive):
        state = "archived"
    elif judged and estimate.probability < cooling:
        state = "cooling"
    elif previous == "cooling" and estimate.probability < cooling * 1.5:
        state = "cooling"
    else:
        state = "active"

    lead.conversion_probability = estimate.probability
    lead.conversion_probability_at = now
    lead.conversion_factors_json = estimate.factors
    lead.engagement_state = state
    if state == "archived" and not lead.kill_signal:
        lead.kill_signal = estimate.kill_signal or "probability_below_archive"

    owner = notifications.owner_of_lead(session, lead)
    if state == "archived" and previous != "archived":
        for enrollment in _enrollments(session, lead.id):
            if enrollment.status is not EnrollmentStatus.STOPPED:
                engine.stop_enrollment(session, enrollment, reason=f"kill_signal:{lead.kill_signal}")
    if state == "cooling" and previous != "cooling":
        until = now + timedelta(days=int(_setting(session, "conversion_cooling_pause_days")))
        for enrollment in _enrollments(session, lead.id):
            if enrollment.status is EnrollmentStatus.ACTIVE:
                engine.pause_enrollment(session, enrollment, until=until)
    _set_tag(session, owner, lead.id, "cooling", "warning", state == "cooling")
    _set_tag(session, owner, lead.id, "archived", "muted", state == "archived")
    session.commit()
    if state != previous:
        logger.info("lead %s: %s -> %s (p=%.4f, kill=%s)", lead.id, previous, state,
                    estimate.probability, lead.kill_signal)
    return state


def send_gate(session: Session, lead: Lead, enrollment: SequenceEnrollment,
              now: datetime | None = None) -> str | None:
    """Called by the send task before rendering. None = send; otherwise the
    send ends here with that status and the sequence has been paused/stopped."""
    if not _setting(session, "conversion_gate_enabled"):
        return None
    estimate = compute(session, lead, now)
    cooling = float(_setting(session, "conversion_cooling_threshold"))
    judged = estimate.unanswered_sends >= int(_setting(session, "conversion_min_unanswered_sends"))
    if not (estimate.kill_signal or (judged and estimate.probability < cooling)):
        return None
    state = reclassify(session, lead, estimate, now)
    return f"held_{state}" if state in ("cooling", "archived") else None


def reactivate(session: Session, lead: Lead, now: datetime | None = None) -> dict:
    """A person overrides the model: resume paused enrollments and clear the
    state. A STOPPED enrollment stays stopped -- stops are irreversible by
    design (sequence_engine.stop_enrollment); re-enroll to contact again."""
    from app.services import notifications  # noqa: PLC0415

    now = now or _now()
    resumed = 0
    for enrollment in _enrollments(session, lead.id):
        if enrollment.status is EnrollmentStatus.PAUSED:
            enrollment.status, enrollment.paused_until = EnrollmentStatus.ACTIVE, None
            for message in session.execute(select(Message).where(
                    Message.sequence_id == enrollment.sequence_id, Message.lead_id == lead.id,
                    Message.status == MessageStatus.SCHEDULED)).scalars():
                message.scheduled_at = now
            resumed += 1
    lead.engagement_state, lead.kill_signal = "active", None
    owner = notifications.owner_of_lead(session, lead)
    _set_tag(session, owner, lead.id, "cooling", "warning", False)
    _set_tag(session, owner, lead.id, "archived", "muted", False)
    session.commit()
    return {"engagement_state": "active", "resumed_enrollments": resumed}


def rescore_active_leads(session: Session, now: datetime | None = None, limit: int = 5000) -> dict:
    now = now or _now()
    if not _setting(session, "conversion_gate_enabled"):
        return {"scored": 0, "changed": 0}
    lead_ids = session.execute(
        select(SequenceEnrollment.lead_id)
        .where(SequenceEnrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]))
        .distinct().limit(limit)
    ).scalars().all()
    scored = changed = 0
    for lead_id in lead_ids:
        lead = session.get(Lead, lead_id)
        if lead is None:
            continue
        try:
            before = lead.engagement_state or "active"
            after = reclassify(session, lead, compute(session, lead, now), now)
            scored += 1
            changed += int(after != before)
        except Exception:  # noqa: BLE001 -- one lead must not end the sweep
            logger.exception("conversion rescore failed for lead %s", lead_id)
            session.rollback()
    return {"scored": scored, "changed": changed}


def stored_out(lead: Lead) -> dict:
    return {
        "conversion_probability": lead.conversion_probability,
        "engagement_state": lead.engagement_state or "active",
        "kill_signal": lead.kill_signal,
        "conversion_probability_at": _aware(lead.conversion_probability_at).isoformat()
        if lead.conversion_probability_at else None,
        "factors": lead.conversion_factors_json or [],
    }
