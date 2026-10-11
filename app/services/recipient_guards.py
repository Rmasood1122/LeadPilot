"""May this PERSON be contacted at all, right now? -- the person-level guards
of the send chokepoint, for the one send that is not a sequence message.

WHY THIS MODULE EXISTS
Every sequence message goes through outreach_tasks.send_message_impl, which
re-checks, at send time and in this order:

    0. a removed lead       lead.status DROPPED (blocked_lead_removed)
       (a CLOSED lead -- won / lost / disqualified -- is refused SEQUENCE
       steps (blocked_lead_closed), and Reply Copilot answers to it are
       cancelled by reply_copilot.send_time_hold; neither is a person-level
       guard, so not here: the post-meeting follow-up is exactly a message
       to a closed lead)
    1. suppression          email, phone AND LinkedIn (lead_tasks.is_suppressed)
    2. F05 exclusions       the account's do-not-contact / customer / ... lists
                            (guardrails.send_block)
    3. F10 departure block  the person is known to have LEFT the company this
                            lead was sourced at (champion_tracker.departure_block)
    4. F10 derived opt-out  an opt-out recorded on the person's EARLIER record
                            (champion_tracker.derived_opt_out)

The post-meeting follow-up email (app/services/meeting_followup.py) is a Gmail
draft the user sends by pressing Send; it is not a Message row and cannot pass
through send_message_impl (its enrollment is deliberately stopped by "Log
Meeting Outcome", and the campaign / window / cap gates are about cold
cadence, not a reply to a call). It used to check suppression on email and
phone only. This function gives it the SAME five guards, calling the SAME
functions the chokepoint calls, so the two cannot drift apart on who may be
contacted. It is not a send path: it decides, it never transmits.

FAILS CLOSED. A lookup error RAISES; the caller refuses the send.

EXEMPT EXCLUSION REASONS. The caller may name F05 exclusion reasons that do
not apply to its message. The meeting follow-up exempts `customer` and
`open_deal`: the CRM sync (guardrails.sync_from_crm, run by crm_tasks) adds
every closed-won lead and every lead with an open deal to those lists, so
without the exemption the thank-you after a won deal, or the next step on an
open one, would be blocked by the deal the meeting just created. F05 exists to
stop PITCHING those accounts cold (see the guardrails module docstring); every
other reason -- do_not_contact, churned, partner, competitor, other -- still
blocks, and EVERY matching exclusion is examined (guardrails.send_blocks), so
an exempt row never hides a non-exempt one. guardrails.upsert_exclusion's
precedence also keeps do_not_contact from being overwritten by a sync. This is a product decision recorded in
docs/program/fixes/send-path-gaps.md for founder confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.db.models import Lead, Strategy

REMOVED = "removed"
SUPPRESSED = "suppressed"
EXCLUDED = "excluded"
LEFT_COMPANY = "left_company"
EARLIER_OPT_OUT = "earlier_opt_out"


@dataclass(frozen=True)
class RecipientBlock:
    kind: str            # one of the five constants above
    reason: str          # human-readable, safe to show the account owner
    audit: dict = field(default_factory=dict)


def person_block(db: Session, lead: Lead, strategy: Strategy | None, *,
                 exempt_exclusion_reasons: tuple[str, ...] = ()) -> RecipientBlock | None:
    """The first person-level guard that blocks `lead`, or None.

    RAISES on any lookup error (the caller must refuse, never send unchecked).
    """
    from app.services import champion_tracker, guardrails, notifications  # noqa: PLC0415
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    from app.db.models import LeadStatus  # noqa: PLC0415

    if lead.status is LeadStatus.DROPPED:
        # Removed by the account (or erased / dropped by the sourcing chain):
        # the chokepoint refuses a dropped lead too (blocked_lead_removed).
        return RecipientBlock(REMOVED, "this lead was removed (status dropped)")

    if is_suppressed(db, lead.email, lead.phone, linkedin=lead.linkedin_url):
        return RecipientBlock(SUPPRESSED, "this contact is on the suppression list")

    # EVERY matching exclusion, not the first: with an exemption, one exempt
    # row (a company-level open_deal from a CRM sync) must not hide a
    # do_not_contact row on the same person (send-path review, finding 1).
    for excluded in guardrails.send_blocks(db, lead, strategy):
        if excluded.reason not in exempt_exclusion_reasons:
            return RecipientBlock(
                EXCLUDED,
                f"this contact is on your exclusion list ({excluded.kind}: {excluded.reason})",
                {"exclusion": excluded.audit()})

    departed = champion_tracker.departure_block(db, lead, strategy)
    if departed is not None:
        where = departed.from_company or "the company"
        return RecipientBlock(
            LEFT_COMPANY, f"this person has left {where}; this address is closed",
            {"move_id": str(departed.id)})

    owner = notifications.owner_of_strategy(db, strategy)
    if owner is None:
        raise champion_tracker.OwnerUnresolved(
            f"no owner for strategy {getattr(strategy, 'id', None)}")
    opted_out = champion_tracker.derived_opt_out(db, lead, owner)
    if opted_out is not None:
        return RecipientBlock(EARLIER_OPT_OUT, opted_out, {"earlier_record": opted_out})
    return None
