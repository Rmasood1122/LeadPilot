"""Warm first emails to the user's OWN contacts, and adding contacts to a
campaign (docs/features/email-network.md, E).

THERE IS NO SEND PATH IN THIS MODULE. Nothing here transmits anything.

  * draft   AI writes a short first email (one model call; the API wraps it
            in metered(), purpose "drafting"). A draft is never sent.
  * save    the user's edited words are SAVED (status approved). Wording that
            claims more of a relationship than the counts show is refused.
  * attach  a SAVED email is attached to the person's LEAD in one of the
            user's campaigns, as that lead's first email. Nothing is enrolled
            or scheduled here: the user launches / enrolls the campaign
            through the normal flow (lawful-basis confirmation, review gate,
            approval, plan), and when the lead's step-1 EMAIL comes due,
            app/workers/outreach_tasks.send_message_impl -- the one send
            chokepoint -- sends the saved words instead of writing new ones,
            through EVERY gate: suppression, F05 exclusions, departures, plan
            holds, Bounce Shield, consent rules, send window, daily send
            approval, caps, the review queue, forbidden phrases, the claim
            check, and build_compliant_email (unsubscribe link, postal
            address, region notice, one-click List-Unsubscribe headers).
  * add_to_campaign
            contacts become ordinary Lead rows (source "email_network",
            status email_found) in a lead batch, and the normal F01
            verification stage (+ finalize) runs on that batch. Only leads it
            marks VERIFIED can be enrolled -- the same rule as every lead.

Ownership is checked on every row (contact, product, strategy, lead) against
the caller; another account's ids answer 404.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ChannelType, EmailContact, EmailNetworkMessage, Lead, LeadBatch, LeadStatus, Message,
    MessageStatus, Product, Strategy, StrategyStatus, User,
)
from app.services import email_network as en
from app.services import email_network_filter as flt

logger = logging.getLogger(__name__)

SUBJECT_MAX = 150
BODY_MAX = 3000
ADD_MAX = 100
LEAD_SOURCE = "email_network"
#: The marker send_message_impl's audit and the lead timeline read.
OPENER_SOURCE = "email_network_saved_opener"

DRAFT, APPROVED, ATTACHED, USED = "draft", "approved", "attached", "used"
_STRATEGY_OK = (StrategyStatus.VERIFIED, StrategyStatus.EXECUTING)

SYSTEM = (
    "You write ONE short first email from a person to someone in THEIR OWN email "
    "contacts. Respond with ONLY a JSON object: {\"subject\": \"...\", \"body\": \"...\"}. "
    "RULES. Plain text. Body under 120 words, subject under 8 words. Warm, direct and "
    "specific to the recipient's role and company. One easy question at the end. No "
    "links, no placeholders in brackets, no signature block and no unsubscribe line "
    "(the system adds the required footer). Never invent facts about the recipient. "
    "RELATIONSHIP: use ONLY the RELATIONSHIP FACTS given. Never claim a meeting, a "
    "call, a conversation, a mutual contact or a shared history that the facts do not "
    "state. If the facts say you have not written to each other, do not imply that you "
    "have spoken. Never say 'last week', 'recently' or give any date the facts do not "
    "support."
)

EMAIL_NETWORK_MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {"subject": {"type": "string"}, "body": {"type": "string"}},
    "required": ["subject", "body"],
    "additionalProperties": False,
}


class MessageError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# Ownership
# --------------------------------------------------------------------------


def own_contact(db: Session, user: User, contact_id) -> EmailContact:
    row = db.execute(select(EmailContact).where(
        EmailContact.id == contact_id, EmailContact.user_id == user.id)).scalar_one_or_none()
    if row is None:
        raise MessageError(404, "Contact not found.")
    return row


def own_product(db: Session, user: User, product_id) -> Product:
    row = db.execute(select(Product).where(
        Product.id == product_id, Product.user_id == user.id)).scalar_one_or_none()
    if row is None:
        raise MessageError(404, "Product not found.")
    return row


def own_message(db: Session, user: User, message_id) -> EmailNetworkMessage:
    row = db.execute(select(EmailNetworkMessage).where(
        EmailNetworkMessage.id == message_id,
        EmailNetworkMessage.user_id == user.id)
        .execution_options(populate_existing=True)).scalar_one_or_none()
    if row is None:
        raise MessageError(404, "Message not found.")
    return row


def _transition(db: Session, msg: EmailNetworkMessage, expected, **values) -> None:
    """Change a row ONLY if its status is still one of `expected` -- a
    conditional UPDATE the database arbitrates (review round M4: with
    expire_on_commit=False an ORM write would happily overwrite what a
    concurrent request committed, e.g. attach an unsaved AI draft). 409 when
    the row changed underneath; the in-memory row is refreshed either way."""
    from sqlalchemy import update  # noqa: PLC0415

    result = db.execute(
        update(EmailNetworkMessage)
        .where(EmailNetworkMessage.id == msg.id, EmailNetworkMessage.user_id == msg.user_id,
               EmailNetworkMessage.status.in_(tuple(expected)))
        .values(**values).execution_options(synchronize_session=False))
    if (result.rowcount or 0) != 1:
        db.rollback()
        db.refresh(msg)
        raise MessageError(409, "This email was changed at the same time (another tab or "
                                "request). Reload and try again.")
    db.commit()
    db.refresh(msg)


def own_strategy(db: Session, user: User, strategy_id) -> Strategy:
    row = db.execute(select(Strategy).join(Product, Product.id == Strategy.product_id)
                     .where(Strategy.id == strategy_id, Product.user_id == user.id)
                     ).scalar_one_or_none()
    if row is None:
        raise MessageError(404, "Campaign not found.")
    return row


def contact_block(db: Session, user: User, contact: EmailContact, *,
                  casl: bool = True) -> str | None:
    """The filters again, NOW (an unsubscribe or exclusion may have landed
    since the import), plus (casl=True) the CASL rule. A reason, or None."""
    reason = flt.static_reason(contact.email, flt.own_identity(db, user))
    if reason is None:
        lists = flt.load_blocklists(db, user.id, [contact.email])
        reason = lists.reason(contact.email,
                              None if contact.company_from_domain else contact.company)
    if reason is not None:
        return f"This person can no longer be contacted ({flt.LABELS[reason]})."
    return en.casl_block(contact) if casl else None


# --------------------------------------------------------------------------
# What a message may say about the relationship (deterministic)
# --------------------------------------------------------------------------

#: Wording that claims a meeting, a call or a conversation (refused for a
#: contact with no two-way email). Common phrases, not every possible one --
#: the help center and spec say exactly that.
_SPOKEN = re.compile(
    r"\b(as (we )?(discussed|agreed|talked about)|as promised|as mentioned (on|over|during)|"
    r"our (last |recent |earlier |previous )?(conversation|call|chat|meeting|talk|discussion|"
    r"lunch|coffee|phone call|catch-up)|"
    r"(great|good|nice|lovely|wonderful|fantastic|a pleasure|so good) (speaking|talking|"
    r"chatting|meeting|seeing|catching up|connecting|reconnecting|to reconnect|to catch up|"
    r"to meet|to see you|to speak|to talk|to chat)|"
    r"pleasure (meeting|speaking|talking|chatting|to meet)|"
    r"(meeting|met|saw|seeing|meet) you (at|last|yesterday|earlier)|"
    r"catch(ing)? up|reconnect(ing)?|"
    r"when we (spoke|talked|met|chatted)|we(\'ve| have)? (spoke|spoken|talked|met|chatted)|"
    r"since we(\'ve| have)? (spoken|talked|met)|"
    r"following up on our|following our (call|conversation|meeting|chat)|"
    r"per our (call|conversation|meeting|discussion|chat)|"
    r"(last|the) time we (spoke|talked|met)|it was (great|good|nice|a pleasure) to|"
    r"thanks?( you)? (so much )?for (taking my call|the call|your call|lunch|dinner|coffee|"
    r"the coffee|meeting|the meeting|having me|chatting|the chat|the conversation|"
    r"speaking with me|talking with me))\b",
    re.I)
_RECENT = re.compile(r"\b(last week|yesterday|the other day|earlier this week|earlier today|"
                     r"this morning|a few days ago|recently (spoke|talked|met|chatted)|"
                     r"just spoke)\b", re.I)


def relationship_problems(contact: EmailContact, subject: str, body: str,
                          now: datetime | None = None) -> list[str]:
    """Wording that claims more than the counts and dates support."""
    text = f"{subject}\n{body}"
    problems = []
    if not contact.two_way and _SPOKEN.search(text):
        problems.append("It says or implies you have spoken, but no two-way email with "
                        "this person was found. Remove that wording.")
    last = en._aware(contact.last_seen)  # noqa: SLF001
    if _RECENT.search(text) and (last is None or (now or _now()) - last > timedelta(days=14)):
        problems.append("It refers to a recent exchange, but your last email with this "
                        "person was not recent. Remove that wording.")
    return problems


class _Facts:
    """The relationship facts of a lead's person, for the send-time checks."""

    def __init__(self, two_way: bool, last_seen, domain: str):
        self.two_way, self.last_seen, self.domain = two_way, last_seen, domain


def _lead_facts(db: Session, lead: Lead, owner_id) -> _Facts | None:
    """For a lead added from the email network: the CURRENT contact row of
    the owning account if it still exists, else what was recorded on the lead
    when it was added. None for any other lead."""
    if lead.source != LEAD_SOURCE or not lead.email:
        return None
    email = flt.normalize_email(lead.email) or lead.email.lower()
    contact = db.execute(select(EmailContact).where(
        EmailContact.user_id == owner_id, EmailContact.email == email)).scalar_one_or_none() \
        if owner_id is not None else None
    if contact is not None:
        return _Facts(contact.two_way, en._aware(contact.last_seen), contact.domain)  # noqa: SLF001
    recorded = (lead.enrichment_json or {}).get(LEAD_SOURCE) or {}
    return _Facts(bool(recorded.get("two_way")), _parse_seen(recorded.get("last_seen")),
                  email.rsplit("@", 1)[-1])


def _parse_seen(value):
    from app.services.email_network_parse import _iso  # noqa: PLC0415

    if not value:
        return None
    if len(str(value)) == 7:                      # "YYYY-MM" (rows added before ISO)
        value = f"{value}-28T00:00:00+00:00"
    return _iso(str(value))


def send_time_wording_problems(db: Session, lead: Lead, owner_id, subject, body,
                               now: datetime | None = None) -> list[str]:
    """Review round M5: the over-claim check AGAIN on the words that will
    actually go out to an email-network lead -- any step, after any reviewer
    edit. RAISES on a lookup error (the send path then retries)."""
    facts = _lead_facts(db, lead, owner_id)
    if facts is None:
        return []
    return relationship_problems(facts, subject or "", body or "", now=now)


def casl_send_block(db: Session, lead: Lead, owner_id, now: datetime | None = None) -> str | None:
    """Review round M3: the CASL two-year rule re-checked AT SEND TIME for an
    email-network lead, from the current contact row (or what was recorded
    when it was added). RAISES on a lookup error (the send path defers)."""
    facts = _lead_facts(db, lead, owner_id)
    if facts is None or not facts.domain.endswith(".ca"):
        return None
    last = facts.last_seen
    if facts.two_way and last is not None and (now or _now()) - last <= en.CASL_WINDOW:
        return None
    return ("CASL: no two-way email with this Canadian address in the last two years "
            "(implied consent from a business relationship lasts two years)")


def hold_if_opener_deleted(db: Session, lead: Lead, message: Message, subject, body,
                           owner_id) -> bool:
    """A lead whose ATTACHED saved first email was deleted (DELETE
    /email-network, a single-contact delete) does not get AI words in its
    place silently: its step-1 email is HELD in the review queue, with the
    words that would go out, for a person to approve, edit or reject. True =
    held (the caller sets AWAITING_REVIEW). Never for any other message."""
    from app.db.models import SendReview  # noqa: PLC0415
    from app.services import send_review  # noqa: PLC0415

    if (message.channel is not ChannelType.EMAIL or message.origin is not None
            or message.step_no != 1 or lead.source != LEAD_SOURCE):
        return False
    if not ((lead.enrichment_json or {}).get(LEAD_SOURCE) or {}).get(en.OPENER_DELETED):
        return False
    if send_review.review_for(db, message.id) is not None:
        return False                 # already decided (or held): the review gate rules
    review = SendReview(
        message_id=message.id, lead_id=lead.id, user_id=owner_id, status=send_review.PENDING,
        triggers_json=[{"code": "email_network_opener_deleted",
                        "label": "Your saved first email was deleted",
                        "detail": "This person's saved first email was deleted from your "
                                  "email contacts; these are the campaign's own words. "
                                  "Approve, edit or reject them."}])
    send_review._snapshot(review, subject, body,  # noqa: SLF001
                          send_review.content_hash(subject, body))
    db.add(review)
    return True


def _facts(contact: EmailContact) -> str:
    _, why = en.relationship(contact, _now())
    return why + "."


# --------------------------------------------------------------------------
# draft / save
# --------------------------------------------------------------------------


def draft(db: Session, user: User, contact_id, product_id) -> EmailNetworkMessage:
    from app.services import anthropic_client, prompt_safety, style_profile  # noqa: PLC0415
    from app.db.models import EmailContactMatch  # noqa: PLC0415

    contact = own_contact(db, user, contact_id)
    product = own_product(db, user, product_id)
    blocked = contact_block(db, user, contact, casl=False)
    if blocked:
        raise MessageError(409, blocked)
    existing = db.execute(select(EmailNetworkMessage).where(
        EmailNetworkMessage.user_id == user.id,
        EmailNetworkMessage.contact_id == contact.id)
        .execution_options(populate_existing=True)).scalar_one_or_none()
    redraftable = (DRAFT, APPROVED) + ((USED,) if existing is not None
                                       and opener_dead(db, existing) else ())
    if existing is not None and existing.status not in redraftable:
        raise MessageError(409, "This email is already attached to a campaign.")
    match = db.execute(select(EmailContactMatch).where(
        EmailContactMatch.user_id == user.id, EmailContactMatch.contact_id == contact.id,
        EmailContactMatch.product_id == product.id)).scalar_one_or_none()
    why = "; ".join(r for r in (match.reasons_json or [])[1:]
                    if not r.startswith("No two-way")) if match else ""
    # F-AI-02: name / title / company come from email headers and contacts
    # files -- anyone can put anything in a display name. Delimited, escaped.
    prompt = "\n".join([
        prompt_safety.NOTICE,
        "WRITE THE EMAIL.",
        "RECIPIENT NAME: " + prompt_safety.inline(contact.full_name or "unknown"),
        "RECIPIENT ROLE: " + prompt_safety.inline(contact.title or "unknown"),
        "RECIPIENT COMPANY: " + prompt_safety.inline(contact.company or "unknown"),
        f"RELATIONSHIP FACTS (the only ones you may use): {_facts(contact)}",
        f"WHAT THE SENDER OFFERS: {product.name}. {(product.description or '')[:600]}",
        f"WHY THIS PERSON MAY BE RELEVANT: {why or 'role and company fit'}",
        "Return the JSON object now.",
    ])
    try:
        data = anthropic_client.get_client().complete_json(
            system=SYSTEM + style_profile.system_suffix(user.style_profile_json),
            prompt=prompt, max_tokens=700,
            schema=EMAIL_NETWORK_MESSAGE_SCHEMA)
    except Exception as exc:  # noqa: BLE001
        raise MessageError(502, "The writer is unavailable. Try again.") from exc
    subject = " ".join(str((data or {}).get("subject") or "").split())[:SUBJECT_MAX]
    body = str((data or {}).get("body") or "").strip()[:BODY_MAX]
    if not body:
        raise MessageError(502, "The writer returned nothing. Try again.")
    subject = subject or "Quick question"
    if existing is None:
        existing = EmailNetworkMessage(user_id=user.id, contact_id=contact.id,
                                       product_id=product.id, subject=subject, body=body,
                                       status=DRAFT)
        db.add(existing)
        db.commit()
    else:
        _transition(db, existing, redraftable, product_id=product.id, subject=subject,
                    body=body, status=DRAFT, error=None, strategy_id=None, lead_id=None,
                    message_id=None)
    return existing


def save(db: Session, user: User, message_id, subject: str, body: str) -> EmailNetworkMessage:
    msg = own_message(db, user, message_id)
    if msg.status in (ATTACHED, USED):
        raise MessageError(409, "Detach this email from its campaign before editing it."
                           if msg.status == ATTACHED else "This email was already used.")
    subject = " ".join((subject or "").split())
    body = (body or "").strip()
    if not subject or len(subject) > SUBJECT_MAX:
        raise MessageError(422, f"The subject must be 1 to {SUBJECT_MAX} characters.")
    if not body or len(body) > BODY_MAX:
        raise MessageError(422, f"The email must be 1 to {BODY_MAX} characters.")
    contact = own_contact(db, user, msg.contact_id)
    problems = relationship_problems(contact, subject, body)
    if problems:
        raise MessageError(422, " ".join(problems))
    _transition(db, msg, (DRAFT, APPROVED), subject=subject, body=body, status=APPROVED,
                error=None)
    return msg


# --------------------------------------------------------------------------
# add to campaign (leads + the normal verification stage)
# --------------------------------------------------------------------------


def _check_strategy(db: Session, user: User, strategy_id) -> Strategy:
    strategy = own_strategy(db, user, strategy_id)
    if strategy.status not in _STRATEGY_OK:
        raise MessageError(409, "That campaign's strategy is not verified yet.")
    return strategy


def _lead_for(db: Session, strategy: Strategy, email: str) -> Lead | None:
    from sqlalchemy import func  # noqa: PLC0415

    return db.execute(select(Lead).where(Lead.strategy_id == strategy.id,
                                         func.lower(Lead.email) == email)).scalars().first()


def add_to_campaign(db: Session, user: User, strategy_id, contact_ids) -> dict:
    """Create leads for these contacts in one of the user's campaigns and a
    lead batch for the normal verification stage. Returns what happened per
    contact and the batch id the caller enqueues (None = nothing added).
    Commits."""
    from app.services import provenance  # noqa: PLC0415
    from app.workers.lead_tasks import strategy_lead_room  # noqa: PLC0415
    from app.config import settings  # noqa: PLC0415

    ids = list(dict.fromkeys(contact_ids or []))
    if not ids or len(ids) > ADD_MAX:
        raise MessageError(422, f"Choose 1 to {ADD_MAX} contacts.")
    strategy = _check_strategy(db, user, strategy_id)
    contacts = [own_contact(db, user, cid) for cid in ids]          # 404 on any foreign id
    room = strategy_lead_room(db, strategy.id)
    skipped: list[dict] = []
    wanted: list[EmailContact] = []
    for contact in contacts:
        blocked = contact_block(db, user, contact)
        if blocked:
            skipped.append({"contact_id": str(contact.id), "reason": blocked})
        elif _lead_for(db, strategy, contact.email) is not None:
            skipped.append({"contact_id": str(contact.id),
                            "reason": "Already a lead in this campaign."})
        elif room is not None and len(wanted) >= room:
            skipped.append({"contact_id": str(contact.id),
                            "reason": "Your plan's lead limit for this campaign is reached."})
        else:
            wanted.append(contact)
    if not wanted:
        return {"added": 0, "skipped": skipped, "batch_id": None, "lead_ids": {}}
    batch = LeadBatch(strategy_id=strategy.id, requested_leads=len(wanted),
                      icp_criteria_json=None, source_provider=LEAD_SOURCE,
                      verifier_provider=settings.email_verifier_provider)
    from app.db.models import BatchStage  # noqa: PLC0415

    batch.stage = BatchStage.VERIFYING
    db.add(batch)
    db.flush()
    leads: dict[str, str] = {}
    for contact in wanted:
        lead = Lead(
            strategy_id=strategy.id, batch_id=batch.id, source=LEAD_SOURCE, external_id=None,
            full_name=(contact.full_name or None) and contact.full_name[:200],
            title=(contact.title or None) and contact.title[:200],
            company=(contact.company or None) and contact.company[:200],
            email=contact.email, status=LeadStatus.EMAIL_FOUND,
            enrichment_json={
                "company_domain": contact.domain,
                # Review round H2: the country the address's ccTLD names, so
                # the region rules (notice, no tracking pixel in the EU/UK)
                # apply; unknown stays unknown and is treated as strictest.
                **({"country": country, "country_source": "email_domain"}
                   if (country := country_for_domain(contact.domain)) else {}),
                LEAD_SOURCE: {"contact_id": str(contact.id), "two_way": contact.two_way,
                              "last_seen": (en._aware(contact.last_seen).isoformat()  # noqa: SLF001
                                            if contact.last_seen else None)},
            })
        db.add(lead)
        db.flush()
        detail = "your own email contacts (imported by you)"
        entries = {f: {"source": provenance.IMPORT, "value": v, "detail": detail}
                   for f, v in (("full_name", lead.full_name), ("title", lead.title),
                                ("email", lead.email)) if v}
        if lead.company:
            entries["company"] = {
                "source": provenance.INFERRED if contact.company_from_domain else provenance.IMPORT,
                "value": lead.company,
                "detail": ("guessed from the email domain" if contact.company_from_domain
                           else detail)}
        provenance.record_many(db, lead, entries, commit=False)
        leads[str(contact.id)] = str(lead.id)
    db.commit()
    return {"added": len(wanted), "skipped": skipped, "batch_id": str(batch.id),
            "lead_ids": leads}


# --------------------------------------------------------------------------
# attach a saved email to a lead (nothing is sent here)
# --------------------------------------------------------------------------


#: Two-letter TLDs used generically (not a statement about the country).
_GENERIC_CCTLDS = frozenset({"io", "co", "ai", "me", "tv", "ly", "fm", "gg", "to", "so",
                             "sh", "ws", "cc", "am", "la", "gl", "vc", "nu", "ac"})


def country_for_domain(domain: str) -> str | None:
    """'feuerschutz-gmbh.de' -> 'DE', 'acme.co.uk' -> 'GB', 'acme.com' -> None."""
    tld = (domain or "").rsplit(".", 1)[-1].lower()
    if tld == "uk":
        return "GB"
    if len(tld) != 2 or not tld.isalpha() or tld in _GENERIC_CCTLDS:
        return None
    return tld.upper()


def _first_email_taken(db: Session, lead: Lead) -> bool:
    """A step-1 email for this lead already exists (scheduled, held or sent)."""
    return db.execute(select(Message.id).where(
        Message.lead_id == lead.id, Message.step_no == 1, Message.origin.is_(None),
        Message.channel == ChannelType.EMAIL,
        Message.status != MessageStatus.CANCELLED)).first() is not None


def attach(db: Session, user: User, message_id, strategy_id) -> tuple[EmailNetworkMessage, str | None]:
    """Attach a SAVED email to the contact's lead in one of the user's
    campaigns (creating the lead -- and its verification batch -- if needed).
    Returns (message, batch id to enqueue or None). Commits."""
    msg = own_message(db, user, message_id)
    if msg.status != APPROVED:
        raise MessageError(409, "Only a saved email can be attached. Save it first."
                           if msg.status == DRAFT else "This email is already attached.")
    contact = own_contact(db, user, msg.contact_id)
    blocked = contact_block(db, user, contact)
    if blocked:
        raise MessageError(409, blocked)
    strategy = _check_strategy(db, user, strategy_id)
    batch_id = None
    lead = _lead_for(db, strategy, contact.email)
    if lead is None:
        added = add_to_campaign(db, user, strategy.id, [contact.id])
        if not added["added"]:
            raise MessageError(409, added["skipped"][0]["reason"])
        lead = db.get(Lead, uuid.UUID(added["lead_ids"][str(contact.id)]))
        batch_id = added["batch_id"]
    if lead.status is LeadStatus.DROPPED:
        raise MessageError(409, "This person was removed from that campaign.")
    if _first_email_taken(db, lead):
        raise MessageError(409, "This person's first email in that campaign is already "
                                "scheduled or sent.")
    other = db.execute(select(EmailNetworkMessage).where(
        EmailNetworkMessage.lead_id == lead.id, EmailNetworkMessage.id != msg.id,
        EmailNetworkMessage.status.in_((ATTACHED, USED)))).first()
    if other is not None:
        raise MessageError(409, "Another saved email is already attached to this lead.")
    _transition(db, msg, (APPROVED,), strategy_id=strategy.id, lead_id=lead.id,
                status=ATTACHED, error=None)
    return msg, batch_id


def opener_dead(db: Session, msg: EmailNetworkMessage) -> bool:
    """A USED first email whose campaign message was rejected in review,
    cancelled or failed: nothing went out, so the contact may be written to
    again (review round LOW)."""
    if msg.status != USED or msg.message_id is None:
        return False
    linked = db.get(Message, msg.message_id)
    return linked is None or linked.status in (MessageStatus.CANCELLED, MessageStatus.FAILED)


def detach(db: Session, user: User, message_id) -> EmailNetworkMessage:
    msg = own_message(db, user, message_id)
    if msg.status == USED and not opener_dead(db, msg):
        raise MessageError(409, "This email was already used for the campaign's first email.")
    if msg.status not in (ATTACHED, USED):
        raise MessageError(409, "This email is not attached to a campaign.")
    _transition(db, msg, (msg.status,), status=APPROVED, strategy_id=None, lead_id=None,
                message_id=None)
    return msg


# --------------------------------------------------------------------------
# The send chokepoint's side (called from outreach_tasks, inside its gates)
# --------------------------------------------------------------------------


def saved_opener(db: Session, message: Message, lead: Lead, strategy: Strategy):
    """The user's saved words for this lead's FIRST campaign email, or None
    (then the step is written as usual). Only a step-1 EMAIL of a sequence
    (origin NULL) qualifies, only for a row of the account that owns the
    campaign. Marks the row used and links it to the message; the caller
    commits. Raises on a lookup error (the send path then retries later --
    nothing is sent unchecked)."""
    from app.services import notifications  # noqa: PLC0415

    if (message.channel is not ChannelType.EMAIL or message.origin is not None
            or message.step_no != 1):
        return None
    from sqlalchemy import or_, update  # noqa: PLC0415

    row = db.execute(select(EmailNetworkMessage).where(
        EmailNetworkMessage.lead_id == lead.id,
        EmailNetworkMessage.status.in_((ATTACHED, USED)),
    ).order_by(EmailNetworkMessage.created_at)
        .execution_options(populate_existing=True)).scalars().first()
    if row is None:
        return None
    if row.message_id is not None and row.message_id != message.id:
        return None                    # already used for a different message
    if row.user_id != notifications.owner_of_strategy(db, strategy):
        logger.warning("saved opener %s ignored: owner mismatch", row.id)
        return None
    # Conditional (review M4): only a row still attached -- or already used
    # for THIS message (a retry) -- is taken; a concurrent detach wins.
    claimed = db.execute(
        update(EmailNetworkMessage)
        .where(EmailNetworkMessage.id == row.id,
               EmailNetworkMessage.status.in_((ATTACHED, USED)),
               or_(EmailNetworkMessage.message_id.is_(None),
                   EmailNetworkMessage.message_id == message.id))
        .values(status=USED, message_id=message.id)
        .execution_options(synchronize_session=False))
    if (claimed.rowcount or 0) != 1:
        return None
    return row.subject, row.body


def message_out(db: Session, m: EmailNetworkMessage) -> dict:
    sent = None
    if m.message_id is not None:
        linked = db.get(Message, m.message_id)
        sent = linked.status.value if linked is not None else None
    return {"id": str(m.id), "contact_id": str(m.contact_id), "product_id": str(m.product_id),
            "subject": m.subject, "body": m.body, "status": m.status,
            "strategy_id": str(m.strategy_id) if m.strategy_id else None,
            "lead_id": str(m.lead_id) if m.lead_id else None,
            "campaign_message_status": sent, "error": m.error}
