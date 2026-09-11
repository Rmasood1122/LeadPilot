"""Feature Group 7 — "Log Meeting Outcome" and the follow-up email it drafts.

WHAT ONE SUBMISSION DOES, IN ORDER
  1. Moves the lead to the post-meeting status for the outcome, records a
     MeetingOutcome row with the before/after, and writes the CRM activity and
     a note carrying the user's meeting notes.
  2. Stops every live enrollment for the lead. A meeting on LeadPilot's own
     calendar only PAUSED the cold sequence (sequence_engine.pause_for_meeting)
     so a cancellation could resume it; once a human has logged how the call
     went, resuming cold outreach a day later would be absurd whatever the
     outcome. This is the "a human recorded the outcome" stop that pause's
     docstring anticipates.
  3. closed_won creates a Deal (revenue for Feature Group 3) and writes
     OutcomeEvent.WON; closed_lost writes OutcomeEvent.LOST -- the learning
     loop has had those event types since M1 and nothing wrote them.
  4. Commits. Everything above is durable before the model is called.
  5. Generates the follow-up email with Claude and saves it as a Gmail DRAFT.
     Never sent automatically: the user reviews it, edits it if they like, and
     presses Send (or sends from Gmail).

Steps 5's failures are recorded on the row (`draft_status`) rather than
raised. A model timeout or a Gmail grant missing the compose scope must not
lose the outcome the user just logged -- the lead page shows what happened and
offers a retry.

SUPPRESSION
Drafting and sending both re-check the suppression list. A person who
unsubscribed does not get a follow-up because they took a call first.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    CrmActivityKind,
    CrmNote,
    Deal,
    DealStage,
    EnrollmentStatus,
    GmailAccount,
    Lead,
    LeadStatus,
    Meeting,
    MeetingOutcome,
    MeetingOutcomeKind,
    Message,
    Outcome,
    OutcomeEvent,
    Product,
    SequenceEnrollment,
    Strategy,
    User,
)
from app.services import anthropic_client

logger = logging.getLogger(__name__)

OUTCOME_STATUS: dict[MeetingOutcomeKind, LeadStatus] = {
    MeetingOutcomeKind.INTERESTED: LeadStatus.OPPORTUNITY,
    MeetingOutcomeKind.NEEDS_FOLLOW_UP: LeadStatus.OPPORTUNITY,
    MeetingOutcomeKind.NOT_A_FIT: LeadStatus.DISQUALIFIED,
    MeetingOutcomeKind.CLOSED_WON: LeadStatus.CLOSED_WON,
    MeetingOutcomeKind.CLOSED_LOST: LeadStatus.CLOSED_LOST,
}

OUTCOME_LABELS: dict[MeetingOutcomeKind, str] = {
    MeetingOutcomeKind.INTERESTED: "Interested",
    MeetingOutcomeKind.NEEDS_FOLLOW_UP: "Needs follow-up",
    MeetingOutcomeKind.NOT_A_FIT: "Not a fit",
    MeetingOutcomeKind.CLOSED_WON: "Closed won",
    MeetingOutcomeKind.CLOSED_LOST: "Closed lost",
}

# Days until the CRM's "next action" for outcomes that need another touch.
NEXT_ACTION_DAYS = {
    MeetingOutcomeKind.INTERESTED: 2,
    MeetingOutcomeKind.NEEDS_FOLLOW_UP: 3,
}

_GUIDANCE = {
    MeetingOutcomeKind.INTERESTED: (
        "They are interested. Thank them, recap in two or three lines what "
        "THEY said mattered, confirm the next step that was agreed in the "
        "notes, and end with one clear, low-friction call to action."),
    MeetingOutcomeKind.NEEDS_FOLLOW_UP: (
        "The call left something open. Thank them, recap briefly, answer or "
        "acknowledge the open question from the notes, and propose one "
        "specific next touch."),
    MeetingOutcomeKind.NOT_A_FIT: (
        "It is not a fit. Thank them for their time, say so honestly and "
        "briefly, leave the door open, and do NOT pitch."),
    MeetingOutcomeKind.CLOSED_WON: (
        "They said yes. Thank them, confirm what happens next exactly as the "
        "notes describe it (onboarding, paperwork, kickoff), and welcome "
        "them. No selling."),
    MeetingOutcomeKind.CLOSED_LOST: (
        "They said no. Thank them, respect the decision, ask ONE short "
        "question that would help you improve, and leave the door open."),
}

SYSTEM = (
    "You are LeadPilot's post-meeting follow-up writer. You write the one "
    "email a seller sends a prospect after a sales call. Respond with ONLY a "
    'JSON object: {"subject": "...", "body": "..."}. RULES. Plain text body, '
    "under 180 words, no subject line inside the body, no placeholders like "
    "[Name]. Never state a commitment, price, date or fact that is not in the "
    "meeting notes or the material given -- if the notes do not say what was "
    "agreed, do not invent it; keep the email general instead. Address the "
    "prospect by first name. Sign off with the seller's first name if it is "
    "given, otherwise with no name. If a writing style profile is given, "
    "match it."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _cents(value) -> int:
    if value is None:
        return 0
    return max(0, int(round(float(value) * 100)))


def _stop_live_enrollments(db: Session, lead: Lead, reason: str) -> int:
    from app.services import sequence_engine as engine  # noqa: PLC0415

    stopped = 0
    for enrollment in db.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.lead_id == lead.id)
    ).scalars().all():
        if enrollment.status is not EnrollmentStatus.STOPPED:
            engine.stop_enrollment(db, enrollment, reason=reason)
            stopped += 1
    return stopped


def log_outcome(db: Session, *, user: User, lead: Lead,
                outcome: MeetingOutcomeKind, notes: str | None = None,
                meeting_id: uuid.UUID | None = None, deal_value=None,
                currency: str = "USD", deal_name: str | None = None,
                now: datetime | None = None) -> MeetingOutcome:
    """Steps 1-4 of the module docstring. Commits. Does not call the model."""
    from app.services import crm_events, meeting_prep  # noqa: PLC0415
    from app.services.crm_service import get_or_create_meta  # noqa: PLC0415

    now = now or _now()
    previous = lead.status
    new_status = OUTCOME_STATUS[outcome]
    lead.status = new_status
    brief = meeting_prep.latest_for_lead(db, lead.id, now=now)

    row = MeetingOutcome(
        lead_id=lead.id, user_id=user.id, meeting_id=meeting_id,
        brief_id=brief.id if brief else None, outcome=outcome,
        notes=(notes or "").strip()[:20_000] or None,
        previous_status=previous.value if previous else None,
        new_status=new_status.value, draft_status="pending",
    )
    db.add(row)
    db.flush()

    if outcome in (MeetingOutcomeKind.CLOSED_WON, MeetingOutcomeKind.CLOSED_LOST):
        db.add(Outcome(
            lead_id=lead.id, strategy_id=lead.strategy_id,
            event=(OutcomeEvent.WON if outcome is MeetingOutcomeKind.CLOSED_WON
                   else OutcomeEvent.LOST),
            channel="meeting",
            meta_json={"meeting_outcome_id": str(row.id)},
        ))

    if outcome is MeetingOutcomeKind.CLOSED_WON:
        deal = Deal(
            user_id=user.id, lead_id=lead.id, strategy_id=lead.strategy_id,
            name=(deal_name or f"{lead.company or lead.full_name or 'Deal'} — won")[:200],
            value_cents=_cents(deal_value), currency=(currency or "USD").upper()[:3],
            stage=DealStage.WON, close_date=now.date(), source="meeting_outcome",
        )
        db.add(deal)
        db.flush()
        row.deal_id = deal.id
        crm_events.record_activity(
            db, lead.id, CrmActivityKind.DEAL_CREATED, actor_user_id=user.id,
            to_value=f"{deal.value_cents / 100:.2f} {deal.currency}",
            meta={"deal_id": str(deal.id), "source": "meeting_outcome"},
        )

    if outcome in NEXT_ACTION_DAYS:
        meta = get_or_create_meta(db, lead)
        meta.next_action_at = now + timedelta(days=NEXT_ACTION_DAYS[outcome])

    crm_events.record_activity(
        db, lead.id, CrmActivityKind.MEETING_OUTCOME_LOGGED,
        actor_user_id=user.id,
        from_value=previous.value if previous else None,
        to_value=new_status.value,
        meta={"outcome": outcome.value, "meeting_outcome_id": str(row.id),
              "meeting_id": str(meeting_id) if meeting_id else None},
    )
    if row.notes:
        db.add(CrmNote(lead_id=lead.id, author_user_id=user.id,
                       body=f"Meeting notes — {OUTCOME_LABELS[outcome]}:\n\n"
                            f"{row.notes}"[:10_000]))
    db.commit()

    _stop_live_enrollments(db, lead, reason=f"meeting_outcome_{outcome.value}")
    db.commit()

    if outcome is MeetingOutcomeKind.CLOSED_WON:
        _announce_won(db, user, lead, row)
    return row


def _announce_won(db: Session, user: User, lead: Lead, row: MeetingOutcome) -> None:
    from app.workers.notification_tasks import enqueue_event  # noqa: PLC0415

    deal = db.get(Deal, row.deal_id) if row.deal_id else None
    value = f"{deal.value_cents / 100:,.2f} {deal.currency}" if deal else ""
    enqueue_event(
        user.id, "deal_won",
        title=f"Closed won: {lead.company or lead.full_name or 'a deal'}",
        body=f"{value} logged from the meeting outcome.".strip(),
        deep_link=f"/leads/detail?id={lead.id}",
        webhook_payload={"lead_id": str(lead.id),
                         "deal_id": str(deal.id) if deal else None,
                         "value_cents": deal.value_cents if deal else 0,
                         "currency": deal.currency if deal else None},
        push=True, slack=True,
    )


# ---------------------------------------------------------------------------
# The follow-up email
# ---------------------------------------------------------------------------


def _latest_thread_ref(db: Session, lead: Lead) -> str | None:
    msg = db.execute(
        select(Message).where(Message.lead_id == lead.id,
                              Message.thread_ref.isnot(None))
        .order_by(Message.sent_at.desc())
    ).scalars().first()
    return msg.thread_ref if msg else None


def build_prompt(db: Session, row: MeetingOutcome, lead: Lead, user: User) -> str:
    from app.services import meeting_prep  # noqa: PLC0415

    strategy = db.get(Strategy, lead.strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    meeting = (db.get(Meeting, row.meeting_id) if row.meeting_id else
               db.execute(select(Meeting).where(Meeting.lead_id == lead.id,
                                                Meeting.summary.isnot(None))
                          .order_by(Meeting.start_at.desc())).scalars().first())
    brief_sections = {}
    if row.brief_id:
        from app.db.models import MeetingPrepBrief  # noqa: PLC0415
        brief = db.get(MeetingPrepBrief, row.brief_id)
        brief_sections = (brief.sections_json or {}) if brief else {}
    profile = meeting_prep.lead_profile(lead)
    seller_name = getattr(user, "display_name", None)
    return "\n".join([
        f"OUTCOME: {OUTCOME_LABELS[row.outcome]}",
        f"WHAT TO DO: {_GUIDANCE[row.outcome]}",
        "",
        f"PROSPECT: {profile.get('name') or 'unknown'} — {profile.get('title') or ''} "
        f"at {profile.get('company') or 'unknown company'}",
        f"SELLER FIRST NAME: {seller_name or '(not given)'}",
        f"WHAT THE SELLER SELLS: "
        f"{(product.name + ' — ' + (product.description or '')) if product else '(unknown)'}",
        "",
        "SELLER'S MEETING NOTES:",
        row.notes or "(none)",
        "",
        "AI MEETING SUMMARY:",
        (meeting.summary if meeting and meeting.summary else "(none)"),
        "",
        "WHY THEY BOOKED (from the prep brief):",
        brief_sections.get("why_they_booked") or "(none)",
        "",
        "STRATEGY EXCERPT:",
        ((strategy.strategy_document or "")[:4000] if strategy else "(none)"),
        "",
        "Return the JSON object now.",
    ])


def generate_email(db: Session, row: MeetingOutcome, lead: Lead, user: User) -> dict:
    # Feature Group 2: the user's voice goes in the SYSTEM prompt, like every
    # other outreach copy call (style_profile.system_suffix).
    from app.services.style_profile import system_suffix  # noqa: PLC0415

    data = anthropic_client.get_client().complete_json(
        system=SYSTEM + system_suffix(getattr(user, "style_profile_json", None)),
        prompt=build_prompt(db, row, lead, user),
        max_tokens=settings.meeting_followup_max_tokens,
    )
    subject = str((data or {}).get("subject") or "").strip()
    body = str((data or {}).get("body") or "").strip()
    if not subject or not body:
        raise ValueError("the model returned an empty follow-up email")
    return {"subject": subject[:300], "body": body[:6000]}


def draft_followup(db: Session, row: MeetingOutcome, *, user: User) -> MeetingOutcome:
    """Step 5: write the email, then save it to Gmail. Records, never raises."""
    lead = db.get(Lead, row.lead_id)
    try:
        email = generate_email(db, row, lead, user)
    except Exception as exc:  # noqa: BLE001 -- recorded on the row
        logger.warning("follow-up generation failed for outcome %s: %s", row.id, exc)
        row.draft_status = "generation_failed"
        row.draft_error = f"{type(exc).__name__}: {exc}"[:2000]
        db.commit()
        return row
    row.followup_subject = email["subject"]
    row.followup_body = email["body"]
    db.commit()
    return save_gmail_draft(db, row, user=user)


def _account_for(db: Session, user: User) -> GmailAccount | None:
    return db.execute(
        select(GmailAccount).where(GmailAccount.user_id == user.id)
    ).scalar_one_or_none()


def save_gmail_draft(db: Session, row: MeetingOutcome, *, user: User) -> MeetingOutcome:
    """Create (or replace) the Gmail draft for this row's email text."""
    from app.integrations import gmail  # noqa: PLC0415
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    lead = db.get(Lead, row.lead_id)
    if not row.followup_subject or not row.followup_body:
        row.draft_status, row.draft_error = "generation_failed", "no email text to save"
    elif not lead.email:
        row.draft_status, row.draft_error = "no_address", "this lead has no email address"
    elif is_suppressed(db, lead.email, lead.phone):
        row.draft_status = "suppressed"
        row.draft_error = "this contact is on the suppression list -- no draft saved"
    else:
        account = _account_for(db, user)
        if account is None:
            row.draft_status = "not_connected"
            row.draft_error = "connect Gmail in Settings to save this as a draft"
        else:
            try:
                kwargs = dict(to=lead.email, subject=row.followup_subject,
                              body=row.followup_body,
                              thread_ref=_latest_thread_ref(db, lead))
                draft = (gmail.update_draft(db, account, row.gmail_draft_id, **kwargs)
                         if row.gmail_draft_id else
                         gmail.create_draft(db, account, **kwargs))
                row.gmail_draft_id = draft.get("id") or row.gmail_draft_id
                row.gmail_message_id = (draft.get("message") or {}).get("id")
                row.draft_status, row.draft_error = "draft_saved", None
            except gmail.GmailScopeMissing as exc:
                row.draft_status, row.draft_error = "reauth_required", str(exc)
            except Exception as exc:  # noqa: BLE001 -- recorded on the row
                logger.warning("gmail draft save failed for outcome %s: %s", row.id, exc)
                row.draft_status = "failed"
                row.draft_error = f"{type(exc).__name__}: {exc}"[:2000]
    db.commit()
    return row


class FollowupNotSendable(Exception):
    pass


def send_followup(db: Session, row: MeetingOutcome, *, user: User,
                  now: datetime | None = None) -> MeetingOutcome:
    """Send the saved draft. Raises FollowupNotSendable with the reason."""
    from app.integrations import gmail  # noqa: PLC0415
    from app.services import crm_events  # noqa: PLC0415
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    lead = db.get(Lead, row.lead_id)
    if row.sent_at is not None:
        raise FollowupNotSendable("this follow-up was already sent")
    if lead.email and is_suppressed(db, lead.email, lead.phone):
        row.draft_status = "suppressed"
        db.commit()
        raise FollowupNotSendable("this contact is on the suppression list")
    if row.draft_status != "draft_saved" or not row.gmail_draft_id:
        raise FollowupNotSendable("save the draft to Gmail first")
    account = _account_for(db, user)
    if account is None:
        raise FollowupNotSendable("Gmail is not connected")
    try:
        sent = gmail.send_draft(db, account, row.gmail_draft_id)
    except gmail.GmailScopeMissing as exc:
        row.draft_status, row.draft_error = "reauth_required", str(exc)
        db.commit()
        raise FollowupNotSendable(str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise FollowupNotSendable(f"Gmail refused the send: {exc}") from exc

    row.sent_at = now or _now()
    row.gmail_message_id = sent.get("id") or row.gmail_message_id
    row.draft_status = "sent"
    crm_events.record_activity(
        db, lead.id, CrmActivityKind.FOLLOWUP_EMAIL_SENT, actor_user_id=user.id,
        to_value=row.followup_subject,
        meta={"meeting_outcome_id": str(row.id)},
    )
    db.commit()
    return row
