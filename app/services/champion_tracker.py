"""F10 -- Champion Tracker + Staleness Check.

Three things, in order of how much they matter:

1. THE DEPARTURE BLOCK (a SAFETY GUARD in the send chokepoint). Once a person
   is confirmed to have left the company a lead was sourced at, every pending
   message to that lead -- and to any lead of the same account carrying the
   same old address -- is cancelled, and the chokepoint cancels any new one.
   A recorded departure (a `champion_moves` row) keeps blocking even if the
   flag is switched off later: it is a fact, and turning a feature off must
   not re-open a departed person's old company mailbox. Dismissing the move
   (a person, with a reason, audited) is the only way to lift it.

2. THE STALENESS HOLD (flag `champion_tracker_enabled`). A message whose
   prospect's title/company was last observed more than
   `champion_staleness_days` ago is HELD in the chokepoint -- FAILED with
   ERROR_PREFIX, the F01 Bounce Shield pattern: kept, visible, releasable.
   NO provider call is made in the send path; the held message IS the
   re-verification request, picked up by the `champion-reverify-held` sweep.

3. THE CHAMPION REFRESH. Past positive repliers and customers are re-verified
   on a budget-capped daily sweep. When one moved, a NEW lead is created at
   the new company (email only after F01 verification, opt-outs carried over,
   guardrails respected) with a `job_change` re-engagement memory plan. Nothing
   is enrolled or sent: a person decides.

REUSE, NOT DUPLICATION
- Re-verification is the sourcing call itself: `LeadSource.enrich` (Apollo
  /people/match, 30-day ResponseCache).
- Every provider call is a row in F01's EnrichmentAttempt ledger
  (step 'champion_*'); the per-account budget is read back from that ledger.
- The new address is found and verified by F01's waterfall (`run_for_lead`).
- The plan is re-engagement memory's (`plan_for_job_change`).

No model call anywhere in this module: no usage_meter scope is needed.
See docs/features/f10-champion-tracker.md.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    ChampionMove,
    Deal,
    DealStage,
    EnrichmentAttempt,
    InboundReply,
    Lead,
    LeadStatus,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    Product,
    ReengagementPlan,
    SequenceEnrollment,
    EnrollmentStatus,
    Strategy,
    SuppressionEntry,
)
from app.integrations.base import RawLead
from app.services import send_holds
from app.services import waterfall_enrichment as wf

logger = logging.getLogger(__name__)

FLAG = "champion_tracker_enabled"
STALE_SETTING = "champion_staleness_days"
RUN_CAP_SETTING = "champion_refresh_run_cap"
ACCOUNT_UNITS_SETTING = "champion_account_monthly_units"

# Below 60 days a re-check could be answered from the 30-day enrichment cache
# and would prove nothing; above a year the check is meaningless.
MIN_STALE_DAYS = 60
MAX_STALE_DAYS = 365

# message.error prefix for an F10 hold or cancellation. release_held matches on
# it, so it is a contract: change it and held messages can no longer be released.
ERROR_PREFIX = send_holds.CHAMPION_TRACKER_PREFIX       # "champion_tracker: "
SEND_RESULT_HELD = "held_role_unverified"
SEND_RESULT_LEFT = "cancelled_left_company"
SEND_RESULT_DEFERRED = "deferred_champion_check_unavailable"
AUDIT_HELD = "held_role_unverified"
AUDIT_LEFT = "blocked_left_company"
AUDIT_DETECTED = "left_company_detected"
AUDIT_CONFIRMED = "role_check_confirmed"
AUDIT_DISMISSED = "champion_move_dismissed"
# sequence_completion maps the "suppressed" prefix to the SUPPRESSED category.
STOP_REASON = "suppressed_left_company"

ROLE_KEY = "role_check"
CHAMPION_KEY = "champion"
LEAD_SOURCE = "champion"

# role_check.state
CURRENT = "current"
CONFIRMED = "confirmed"
TITLE_CHANGED = "title_changed"
LEFT = "left"
DISPUTED = "disputed"          # the provider still reports a move a person dismissed
# role-check outcomes that change no state
NOT_FOUND = "not_found"
INCONCLUSIVE = "inconclusive"
ERROR = "error"
BUDGET_EXHAUSTED = "budget_exhausted"

# Ledger steps. Everything F10 spends is `step LIKE 'champion%'`.
STEP_ROLE = "champion_role"
STEP_EMAIL = "champion_apollo"
STEP_HUNTER = "champion_hunter"
LEDGER_PREFIX = "champion"
# A role check + (for a champion who moved) one finder + two verifications.
ROLE_CHECK_UNITS = 1
EMAIL_LOOKUP_UNITS = 3

# Champion kinds
POSITIVE_REPLY = "positive_reply"
CUSTOMER = "customer"

# champion_moves.outcome
LEAD_CREATED = "lead_created"
NOT_CHAMPION = "not_champion"
SUPPRESSED = "suppressed"
EXCLUDED = "excluded"
EXISTING_LEAD = "existing_lead"
NO_COMPANY = "no_company"
PENDING = "pending"
FAILED = "failed"           # the follow-through could not be finished (old lead gone)
OUTCOMES = (LEAD_CREATED, NOT_CHAMPION, SUPPRESSED, EXCLUDED, EXISTING_LEAD, NO_COMPANY,
            PENDING, FAILED)
# A move whose follow-through crashed is retried by the held sweep for this long,
# then left `pending` -- and visible in GET /champions/moves -- for a person.
PENDING_RETRY_WINDOW = timedelta(days=7)

RETRY_AFTER_NOT_FOUND = timedelta(days=7)
RETRY_AFTER_ERROR = timedelta(days=1)
RETRY_AFTER_BUDGET = timedelta(days=1)
BUDGET_WINDOW = timedelta(days=30)

# Statuses a lead reaches only after it was contacted (for the metric).
_CONTACTED = (LeadStatus.CONTACTED, LeadStatus.REPLIED, LeadStatus.MEETING_BOOKED,
              LeadStatus.PROPOSAL_SENT, LeadStatus.OPPORTUNITY, LeadStatus.CLOSED_WON,
              LeadStatus.CLOSED_LOST, LeadStatus.DISQUALIFIED)
_REPLIED = (LeadStatus.REPLIED, LeadStatus.MEETING_BOOKED, LeadStatus.PROPOSAL_SENT,
            LeadStatus.OPPORTUNITY, LeadStatus.CLOSED_WON, LeadStatus.CLOSED_LOST,
            LeadStatus.DISQUALIFIED)
_MEETING = (LeadStatus.MEETING_BOOKED, LeadStatus.PROPOSAL_SENT, LeadStatus.OPPORTUNITY,
            LeadStatus.CLOSED_WON)


class Refused(ValueError):
    """A human action that would be unsafe or meaningless (-> 409)."""


class OwnerUnresolved(RuntimeError):
    """No account owns this lead's campaign, so nothing can prove the person
    has NOT left. The send path treats this as a failure: it defers (fails
    closed) instead of sending unchecked."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Settings
# --------------------------------------------------------------------------


def enabled(db: Session) -> bool:
    from app.services import system_settings  # noqa: PLC0415

    return bool(system_settings.get(db, FLAG))


def staleness_days(db: Session) -> int:
    from app.services import system_settings  # noqa: PLC0415

    return max(MIN_STALE_DAYS, min(MAX_STALE_DAYS, int(system_settings.get(db, STALE_SETTING))))


def run_cap(db: Session) -> int:
    from app.services import system_settings  # noqa: PLC0415

    return int(system_settings.get(db, RUN_CAP_SETTING))


def account_units_cap(db: Session) -> int:
    from app.services import system_settings  # noqa: PLC0415

    return int(system_settings.get(db, ACCOUNT_UNITS_SETTING))


def settings_out(db: Session) -> dict:
    return {"enabled": enabled(db), "staleness_days": staleness_days(db),
            "run_cap": run_cap(db), "account_monthly_units": account_units_cap(db)}


# --------------------------------------------------------------------------
# Per-lead role-check state (leads.enrichment_json.role_check)
# --------------------------------------------------------------------------


def role_check(lead: Lead) -> dict:
    stored = lead.enrichment_json if isinstance(lead.enrichment_json, dict) else {}
    value = stored.get(ROLE_KEY)
    return dict(value) if isinstance(value, dict) else {}


def is_erased(lead: Lead) -> bool:
    """A GDPR-erased tombstone (app/api/leads.py gdpr_delete_lead)."""
    stored = lead.enrichment_json if isinstance(lead.enrichment_json, dict) else {}
    return bool(stored.get("gdpr_deleted"))


def inactive_reason(lead: Lead) -> str | None:
    """'erased' / 'dropped' for a lead nothing may look up or write to, else None."""
    if is_erased(lead):
        return "erased"
    if lead.status is LeadStatus.DROPPED:
        return "dropped"
    return None


def _set_role_check(lead: Lead, **fields) -> dict:
    if is_erased(lead):
        # Never write anything about a person back onto their erasure tombstone.
        return {}
    current = role_check(lead)
    for key, value in fields.items():
        current[key] = value.isoformat() if isinstance(value, datetime) else value
    # Reassign (not mutate) so the JSON column is seen as changed.
    lead.enrichment_json = {**(lead.enrichment_json or {}), ROLE_KEY: current}
    return current


def champion_info(lead: Lead) -> dict:
    stored = lead.enrichment_json if isinstance(lead.enrichment_json, dict) else {}
    value = stored.get(CHAMPION_KEY)
    return value if isinstance(value, dict) else {}


def role_observed_at(lead: Lead) -> datetime | None:
    """When the lead's title + company were last OBSERVED to be true.

    A role check that confirmed the role (or a person who confirmed it) wins;
    then the provenance timestamp of the title (Part 1 Feature 10); then the
    moment the lead row was written (sourcing stored the title then)."""
    rc = role_check(lead)
    if rc.get("state") in (CURRENT, CONFIRMED):
        observed = wf._parse(rc.get("observed_at"))
        if observed is not None:
            return observed
    provenance = lead.provenance_json if isinstance(lead.provenance_json, dict) else {}
    title = provenance.get("title")
    if isinstance(title, dict):
        observed = wf._parse(title.get("observed_at"))
        if observed is not None:
            return observed
    return _aware(lead.created_at)


# --------------------------------------------------------------------------
# Ownership helpers
# --------------------------------------------------------------------------


def _owned_lead_ids(user_id):
    return (select(Lead.id).join(Strategy, Strategy.id == Lead.strategy_id)
            .join(Product, Product.id == Strategy.product_id)
            .where(Product.user_id == user_id))


def _owner_of_lead(db: Session, lead: Lead):
    from app.services import notifications  # noqa: PLC0415

    return notifications.owner_of_lead(db, lead)


def _same_address_lead_ids(db: Session, owner, email: str | None) -> list[uuid.UUID]:
    """The account's leads carrying this address (any campaign)."""
    if not (email or "").strip():
        return []
    return list(db.execute(
        select(Lead.id).where(Lead.id.in_(_owned_lead_ids(owner)),
                              func.lower(Lead.email) == email.strip().lower())
    ).scalars())


# --------------------------------------------------------------------------
# 1. The departure block (SAFETY GUARD -- not behind the flag)
# --------------------------------------------------------------------------


def active_move(db: Session, owner, lead: Lead) -> ChampionMove | None:
    """The un-dismissed departure covering this lead -- by the lead itself or
    by its address -- in the OWNER's account. Raises on a database error (the
    send path then defers: fails closed)."""
    if owner is None:
        raise OwnerUnresolved(f"no owner for lead {lead.id}")
    clauses = [ChampionMove.old_lead_id == lead.id]
    digest = wf.email_hash(lead.email)
    if digest:
        clauses.append(ChampionMove.old_email_sha256 == digest)
    return db.execute(
        select(ChampionMove)
        .where(ChampionMove.user_id == owner, ChampionMove.dismissed_at.is_(None),
               or_(*clauses))
        .order_by(ChampionMove.detected_at)
        .limit(1)
    ).scalars().first()


def departure_block(db: Session, lead: Lead, strategy: Strategy | None) -> ChampionMove | None:
    """The send-time check. None = this lead is not known to have left."""
    from app.services import notifications  # noqa: PLC0415

    return active_move(db, notifications.owner_of_strategy(db, strategy), lead)


def _left_error(move: ChampionMove) -> str:
    where = move.from_company or "the company"
    return (f"{ERROR_PREFIX}left {where} - this address is closed "
            f"(re-engagement goes to the new company)")[:1000]


def cancel_for_departure(message: Message, move: ChampionMove) -> None:
    """Mark a message cancelled by the departure block (caller audits, commits
    and stops the enrollment)."""
    message.status = MessageStatus.CANCELLED
    message.error = _left_error(move)


# --------------------------------------------------------------------------
# 2. The staleness hold (flag on)
# --------------------------------------------------------------------------


def staleness_hold(db: Session, lead: Lead, now: datetime | None = None) -> str | None:
    """Why a message to this lead must wait for a role check, or None. Pure
    read: no provider call, ever, in the send path."""
    now = now or _now()
    # Local business mode: an imported customer is a consumer, not a role at a
    # company -- there is no role to go stale, and their data must never be
    # sent to a provider for a role check.
    from app.services.local_business import CUSTOMER_SOURCE  # noqa: PLC0415

    if lead.source == CUSTOMER_SOURCE:
        return None
    rc = role_check(lead)
    if rc.get("state") == TITLE_CHANGED:
        return (f"the title on record ({lead.title or 'none'}) differs from the provider's "
                f"({rc.get('observed_title') or 'unknown'}) - confirm the role")[:500]
    if rc.get("state") == DISPUTED:
        return ("the provider still reports a job change that was dismissed - "
                "confirm the role")
    limit = staleness_days(db)
    observed = role_observed_at(lead)
    if observed is not None and now - observed <= timedelta(days=limit):
        return None
    age = f"{max(0, (now - observed).days)} days old" if observed else "of unknown age"
    last = rc.get("last_outcome")
    tail = f" (last check: {last.replace('_', ' ')})" if last else ""
    return (f"role data is {age} (limit {limit}) - re-verification queued{tail}")[:500]


def hold_message(message: Message, reason: str) -> None:
    """Hold (the caller audits and commits). FAILED with the prefix: kept,
    visible, releasable -- never sent, never dropped."""
    message.status = MessageStatus.FAILED
    message.error = f"{ERROR_PREFIX}{reason}"[:1000]


def _held_filter():
    return (Message.status == MessageStatus.FAILED,
            Message.error.like(f"{ERROR_PREFIX}%"))


def release_held(db: Session, lead: Lead, now: datetime | None = None) -> int:
    """Return this lead's held messages to SCHEDULED, due now -- at most one
    per (sequence, step); extra held copies are cancelled (send_holds.release).
    They are re-checked by the full send path; this is not a bypass."""
    return send_holds.release(db, lead.id, ERROR_PREFIX, now or _now())


def cancel_held(db: Session, lead_id, why: str, *, prefixes=None) -> int:
    """Cancel a lead's held messages (this guard's, or any guard's when
    `prefixes` is send_holds.HOLD_PREFIXES). Caller commits."""
    rows = db.execute(select(Message).where(
        Message.lead_id == lead_id,
        send_holds.held_clause(prefixes or (ERROR_PREFIX,)))).scalars().all()
    for message in rows:
        message.status = MessageStatus.CANCELLED
        message.error = f"{ERROR_PREFIX}{why}"[:1000]
    return len(rows)


def held_messages(db: Session, lead: Lead) -> list[Message]:
    return list(db.execute(
        select(Message).where(Message.lead_id == lead.id, *_held_filter())
        .order_by(Message.scheduled_at)).scalars())


# --------------------------------------------------------------------------
# Budget (read back from F01's ledger)
# --------------------------------------------------------------------------


def units_used(db: Session, owner, now: datetime | None = None) -> int:
    now = now or _now()
    total = db.execute(
        select(func.coalesce(func.sum(EnrichmentAttempt.cost_units), 0))
        .where(EnrichmentAttempt.user_id == owner,
               EnrichmentAttempt.step.like(f"{LEDGER_PREFIX}%"),
               EnrichmentAttempt.created_at >= now - BUDGET_WINDOW)
    ).scalar_one()
    return int(total or 0)


def budget_remaining(db: Session, owner, now: datetime | None = None) -> int:
    return max(0, account_units_cap(db) - units_used(db, owner, now))


# --------------------------------------------------------------------------
# Who is a champion, who opted out
# --------------------------------------------------------------------------


def champion_kind(db: Session, lead: Lead, owner) -> str | None:
    """customer | positive_reply | None. A re-engagement lead inherits the
    kind of the relationship it continues."""
    if lead.status is LeadStatus.CLOSED_WON:
        return CUSTOMER
    if owner is not None and db.execute(
            select(Deal.id).where(Deal.user_id == owner, Deal.lead_id == lead.id,
                                  Deal.stage == DealStage.WON).limit(1)).first():
        return CUSTOMER
    if db.execute(select(InboundReply.id).where(
            InboundReply.lead_id == lead.id,
            InboundReply.intent_label == "interested").limit(1)).first():
        return POSITIVE_REPLY
    inherited = champion_info(lead).get("champion_kind")
    return inherited if inherited in (CUSTOMER, POSITIVE_REPLY) else None


def _person_suppressed(db: Session, lead: Lead) -> bool:
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    return is_suppressed(db, lead.email, lead.phone, linkedin=lead.linkedin_url)


def opt_out_reason(db: Session, lead: Lead) -> str | None:
    """Why this PERSON must not be re-created anywhere, or None. Suppression
    is keyed by address/number/profile, so an opt-out under the old address
    has to be carried to the person explicitly."""
    if _person_suppressed(db, lead):
        return "on the suppression list"
    event = db.execute(
        select(Outcome.event).where(
            Outcome.lead_id == lead.id,
            Outcome.event.in_([OutcomeEvent.UNSUBSCRIBED, OutcomeEvent.OPTED_OUT])).limit(1)
    ).scalar_one_or_none()
    if event is not None:
        return f"{event.value} earlier"
    if (lead.kill_signal or "") == "unsubscribed":
        return "unsubscribed earlier"
    return None


# How far back a chain of moves is followed (old -> new -> newer ...).
_MAX_CHAIN = 10


def derived_opt_out(db: Session, lead: Lead, owner) -> str | None:
    """For a lead created FROM a move: why the person behind it may not be
    contacted, judged on every earlier record of them, NOW.

    Suppression is keyed by address, so an unsubscribe, an opt-out or a
    suppression recorded on the OLD lead / old address after the move would
    otherwise never reach the new lead. Checked at send time (and before any
    re-verification spend) rather than copied at event time: there is no
    event path to forget. Walks the chain of moves back, owner-scoped."""
    seen: set = {lead.id}
    current = lead.id
    for _ in range(_MAX_CHAIN):
        move = db.execute(select(ChampionMove).where(
            ChampionMove.user_id == owner, ChampionMove.new_lead_id == current)
            .order_by(ChampionMove.detected_at)).scalars().first()
        if move is None or move.old_lead_id is None or move.old_lead_id in seen:
            return None
        old = db.get(Lead, move.old_lead_id)
        if old is None:
            return None
        if is_erased(old):
            return "the person's earlier record was erased (GDPR)"
        reason = opt_out_reason(db, old)
        if reason:
            return f"the person is {reason} on their earlier record"
        seen.add(old.id)
        current = old.id
    return None


def linked_lead_ids(db: Session, owner, lead_id) -> set:
    """Every lead of the same person connected to `lead_id` through this
    account's moves (both directions, transitively), excluding `lead_id`."""
    found = {lead_id}
    frontier = {lead_id}
    for _ in range(_MAX_CHAIN):
        if not frontier:
            break
        rows = db.execute(select(ChampionMove.old_lead_id, ChampionMove.new_lead_id).where(
            ChampionMove.user_id == owner,
            or_(ChampionMove.old_lead_id.in_(frontier),
                ChampionMove.new_lead_id.in_(frontier)))).all()
        nxt = {x for row in rows for x in row if x is not None} - found
        found |= nxt
        frontier = nxt
    return found - {lead_id}


# --------------------------------------------------------------------------
# Reading the provider's answer
# --------------------------------------------------------------------------


@dataclass
class Person:
    title: str | None = None
    company: str | None = None
    domain: str | None = None
    email: str | None = None
    external_id: str | None = None
    full_name: str | None = None
    linkedin_url: str | None = None


def read_person(enrichment) -> Person | None:
    """The provider's OWN person record. Never the adapter's merged fields:
    ApolloAdapter.enrich falls back to what we already had for a missing
    title/company/email, which would always 'confirm' the old company.
    Field names are the existing adapter's mapping (UNVERIFIED -- see spec)."""
    from app.integrations.apollo import _LOCKED_EMAIL_MARKERS  # noqa: PLC0415
    from app.services.guardrails import normalize_domain  # noqa: PLC0415

    data = enrichment if isinstance(enrichment, dict) else {}
    person = data.get("person")
    if not isinstance(person, dict) or not person:
        return None
    org = person.get("organization") if isinstance(person.get("organization"), dict) else {}
    email = (person.get("email") or "").strip() or None
    if email and any(marker in email for marker in _LOCKED_EMAIL_MARKERS):
        email = None
    return Person(
        title=(str(person.get("title")).strip()[:200] or None) if person.get("title") else None,
        company=(str(org.get("name")).strip()[:200] or None) if org.get("name") else None,
        domain=normalize_domain(org.get("primary_domain") or org.get("website_url")),
        email=email,
        external_id=str(person["id"]) if person.get("id") is not None else None,
        full_name=person.get("name"),
        linkedin_url=person.get("linkedin_url"),
    )


_TITLE_SYNONYMS = (("vice president", "vp"), ("chief executive officer", "ceo"),
                   ("chief technology officer", "cto"), ("chief operating officer", "coo"),
                   ("chief financial officer", "cfo"), ("chief marketing officer", "cmo"))
_TITLE_WORDS = {"sr": "senior", "jr": "junior", "mgr": "manager", "dir": "director"}
_TITLE_STOP = {"of", "and", "the", "for", "at", "in"}


def _norm_title(value: str | None) -> frozenset[str]:
    text = (value or "").lower().replace("&", " and ")
    for long, short in _TITLE_SYNONYMS:
        text = text.replace(long, short)
    words = re.sub(r"[^\w\s]", " ", text).replace("_", " ").split()
    return frozenset(_TITLE_WORDS.get(w, w) for w in words if w not in _TITLE_STOP)


def compare(lead: Lead, person: Person | None) -> str:
    """current | title_changed | left | not_found | inconclusive."""
    from app.services.guardrails import normalize_company, normalize_domain  # noqa: PLC0415

    if person is None:
        return NOT_FOUND
    old_domain = normalize_domain((lead.enrichment_json or {}).get("company_domain"))
    old_name, new_name = normalize_company(lead.company), normalize_company(person.company)
    checks = []
    if old_domain and person.domain:
        checks.append(old_domain == person.domain)
    if old_name and new_name:
        checks.append(old_name == new_name)
    if not checks:
        return INCONCLUSIVE
    if not any(checks):
        return LEFT                      # every comparison we could make differs
    if not person.title:
        return INCONCLUSIVE if lead.title else CURRENT
    if not lead.title or _norm_title(lead.title) == _norm_title(person.title):
        return CURRENT
    return TITLE_CHANGED


def _raw_for(lead: Lead, source) -> RawLead | None:
    provider = getattr(source, "provider", None)
    info = champion_info(lead)
    if lead.source == provider and lead.external_id:
        pid = lead.external_id
    elif info.get("provider") == provider and info.get("person_external_id"):
        pid = info.get("person_external_id")
    else:
        pid = None
    parts = (lead.full_name or "").split()
    if not (pid or lead.email or (parts and lead.company)):
        return None
    return RawLead(source=provider or "unknown", external_id=pid, full_name=lead.full_name,
                   first_name=parts[0] if parts else None,
                   last_name=parts[-1] if len(parts) > 1 else None,
                   title=lead.title, company=lead.company,
                   company_domain=(lead.enrichment_json or {}).get("company_domain"),
                   email=lead.email, raw={})


# --------------------------------------------------------------------------
# 3. One role check
# --------------------------------------------------------------------------


def reverify(db: Session, lead: Lead, source, verifier=None, *, trigger: str,
             now: datetime | None = None) -> dict:
    """Re-verify one lead's role through the lead source. Never sends.

    Returns {"outcome", "released", "move_id"?}. Commits."""
    now = now or _now()
    # Local business mode: a business's imported customer is never looked up.
    from app.services.local_business import is_customer  # noqa: PLC0415

    if is_customer(lead):
        return {"outcome": "customer", "released": 0}
    inactive = inactive_reason(lead)
    if inactive:
        # An erased or dropped person is never looked up and never written to.
        return {"outcome": inactive, "released": 0}
    owner = _owner_of_lead(db, lead)
    if owner is None:
        return {"outcome": "no_owner", "released": 0}
    if active_move(db, owner, lead) is not None:
        # Moved under this lead or under the same address in another lead:
        # held messages go back to the chokepoint, whose departure block
        # cancels and audits them. Nothing is spent.
        return {"outcome": "already_moved", "released": release_held(db, lead, now)}
    if _person_suppressed(db, lead) or derived_opt_out(db, lead, owner):
        # No spend on someone who opted out (under this record or an earlier
        # one). Their held messages go back to the chokepoint, whose
        # suppression checks cancel and audit them.
        return {"outcome": "suppressed", "released": release_held(db, lead, now)}
    if budget_remaining(db, owner, now) < ROLE_CHECK_UNITS:
        _set_role_check(lead, attempted_at=now, retry_after=now + RETRY_AFTER_BUDGET,
                        last_outcome=BUDGET_EXHAUSTED)
        db.commit()
        return {"outcome": BUDGET_EXHAUSTED, "released": 0}

    raw = _raw_for(lead, source)
    if raw is None:
        _set_role_check(lead, attempted_at=now, retry_after=now + RETRY_AFTER_NOT_FOUND,
                        last_outcome=INCONCLUSIVE)
        db.commit()
        return {"outcome": INCONCLUSIVE, "released": 0}

    ctx = wf.context_for_lead(db, lead)
    provider = getattr(source, "provider", "lead_source")
    wf._reset_last_call(source)
    try:
        enriched = source.enrich(raw)
    except Exception as exc:  # noqa: BLE001 -- recorded, retried tomorrow
        logger.warning("champion role check for lead %s failed: %s", lead.id, exc)
        db.rollback()
        wf._ledger(db, ctx, lead, step=STEP_ROLE, provider=provider, operation="role_check",
                   outcome=ERROR)
        lead = db.get(Lead, lead.id)
        _set_role_check(lead, attempted_at=now, retry_after=now + RETRY_AFTER_ERROR,
                        last_outcome=ERROR)
        db.commit()
        return {"outcome": ERROR, "released": 0}
    cached, units = wf._call_cost(source)
    person = read_person(getattr(enriched, "enrichment", None))
    outcome = compare(lead, person)
    wf._ledger(db, ctx, lead, step=STEP_ROLE, provider=provider, operation="role_check",
               outcome=outcome, cached=cached, cost_units=units,
               domain=person.domain if person else None)
    # A cached answer may be as old as the cache allows: count it that old.
    observed = now - timedelta(seconds=settings.cache_ttl_enrichment_seconds) if cached else now
    base = {"attempted_at": now, "last_outcome": outcome, "source": provider,
            "observed_title": person.title if person else None,
            "observed_company": person.company if person else None}

    if outcome in (NOT_FOUND, INCONCLUSIVE):
        _set_role_check(lead, retry_after=now + RETRY_AFTER_NOT_FOUND, **base)
        db.commit()
        return {"outcome": outcome, "released": 0}

    disputed = db.execute(select(ChampionMove.id).where(
        ChampionMove.old_lead_id == lead.id)).first() is not None
    if outcome == LEFT and disputed:
        # A person dismissed this departure before; the provider still says it.
        # Do not decide again on the same data -- hold for a person.
        _set_role_check(lead, state=DISPUTED, checked_at=now, retry_after=None, **base)
        db.commit()
        return {"outcome": DISPUTED, "released": 0}

    if outcome == CURRENT:
        _set_role_check(lead, state=CURRENT, checked_at=now, observed_at=observed,
                        retry_after=None, **base)
        db.commit()
        return {"outcome": CURRENT, "released": release_held(db, lead, now)}

    if outcome == TITLE_CHANGED:
        _set_role_check(lead, state=TITLE_CHANGED, checked_at=now, retry_after=None, **base)
        db.commit()
        return {"outcome": TITLE_CHANGED, "released": 0}

    # LEFT
    _set_role_check(lead, state=LEFT, checked_at=now, observed_at=observed, retry_after=None,
                    **base)
    db.commit()
    move = record_move(db, owner, lead, person, source=source, verifier=verifier,
                       trigger=trigger, cached=cached, now=now)
    return {"outcome": LEFT, "released": 0, "move_id": str(move.id),
            "move_outcome": move.outcome}


# --------------------------------------------------------------------------
# 4. A move
# --------------------------------------------------------------------------


def record_move(db: Session, owner, lead: Lead, person: Person, *, source, verifier,
                trigger: str, cached: bool = False, now: datetime | None = None) -> ChampionMove:
    """Record the departure, close the old address, and (for a champion)
    create the re-engagement lead. Idempotent: UNIQUE(old_lead_id)."""
    now = now or _now()
    existing = db.execute(select(ChampionMove).where(
        ChampionMove.old_lead_id == lead.id)).scalars().first()
    if existing is not None:
        return existing
    kind = champion_kind(db, lead, owner)
    # Always committed as PENDING first: the row alone already blocks the old
    # address at the chokepoint, and if anything below crashes the held sweep
    # finds the PENDING row and finishes it (retry_pending_moves).
    move = ChampionMove(
        user_id=owner, old_lead_id=lead.id, old_email_sha256=wf.email_hash(lead.email),
        champion_kind=kind, from_company=(lead.company or None),
        from_title=(lead.title or None), to_company=person.company, to_title=person.title,
        to_domain=person.domain, trigger=trigger[:20], outcome=PENDING, detected_at=now)
    db.add(move)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.execute(select(ChampionMove).where(
            ChampionMove.old_lead_id == lead.id)).scalars().one()
    return _finish_move(db, owner, lead, move, person, source=source, verifier=verifier,
                        cached=cached, now=now)


def _finish_move(db: Session, owner, lead: Lead, move: ChampionMove, person: Person, *,
                 source, verifier, cached: bool = False, now: datetime | None = None,
                 retry: bool = False) -> ChampionMove:
    """Close the old address and (for a champion) create the re-engagement
    lead, then set the final outcome. Safe to run again on a PENDING move."""
    now = now or _now()
    close_old_address(db, owner, lead, move, now=now, retry=retry)
    if move.champion_kind:
        outcome, new_lead, detail = create_reengagement_lead(
            db, owner, lead, move, person, source=source, verifier=verifier,
            cached=cached, now=now)
        move.outcome = outcome
        move.new_lead_id = new_lead.id if new_lead is not None else None
        move.detail = (detail or None) and detail[:300]
    else:
        move.outcome = NOT_CHAMPION
    db.commit()
    logger.info("champion tracker: lead %s left %s -> %s (%s)", lead.id, move.from_company,
                move.to_company, move.outcome)
    return move


def retry_pending_moves(db: Session, source, verifier=None, *,
                        now: datetime | None = None) -> int:
    """Finish moves whose follow-through crashed after the row committed
    (outcome still PENDING, no derived lead), for PENDING_RETRY_WINDOW.
    Returns how many were finished."""
    now = now or _now()
    rows = db.execute(select(ChampionMove).where(
        ChampionMove.outcome == PENDING, ChampionMove.new_lead_id.is_(None),
        ChampionMove.dismissed_at.is_(None),
        ChampionMove.detected_at >= now - PENDING_RETRY_WINDOW)
        .order_by(ChampionMove.detected_at)).scalars().all()
    finished = 0
    for move in rows:
        try:
            old = db.get(Lead, move.old_lead_id) if move.old_lead_id else None
            if old is None:
                move.outcome = FAILED
                move.detail = "the old lead no longer exists - nothing to finish"
                db.commit()
                continue
            info = champion_info(old)
            provider = getattr(source, "provider", None)
            person = Person(
                title=move.to_title, company=move.to_company, domain=move.to_domain,
                email=None,             # never stored on the move: the finder looks again
                external_id=(old.external_id if old.source == provider
                             else info.get("person_external_id")),
                full_name=old.full_name, linkedin_url=old.linkedin_url)
            _finish_move(db, move.user_id, old, move, person, source=source,
                         verifier=verifier, now=now, retry=True)
            finished += 1
        except Exception:  # noqa: BLE001 -- retried next run, within the window
            logger.exception("champion move %s could not be finished", move.id)
            db.rollback()
    return finished


def close_old_address(db: Session, owner, lead: Lead, move: ChampionMove,
                      now: datetime | None = None, retry: bool = False) -> dict:
    """Every pending message to the old lead -- and to the account's other
    leads with the same address -- is cancelled, their enrollments stopped,
    open re-engagement plans cancelled. The chokepoint guard then blocks any
    message created later."""
    from app.services import compliance_audit, reengagement_memory  # noqa: PLC0415
    from app.services import sequence_engine as engine  # noqa: PLC0415

    now = now or _now()
    lead_ids = {lead.id, *_same_address_lead_ids(db, owner, lead.email)}
    # Every hold counts (F01's and F10's): a held message to the old address
    # must never be released later.
    pending = db.execute(select(Message).where(
        Message.lead_id.in_(lead_ids),
        or_(Message.status.in_([MessageStatus.SCHEDULED, MessageStatus.AWAITING_REVIEW]),
            send_holds.held_clause()))).scalars().all()
    for message in pending:
        cancel_for_departure(message, move)
    db.commit()
    enrollments = db.execute(select(SequenceEnrollment).where(
        SequenceEnrollment.lead_id.in_(lead_ids),
        SequenceEnrollment.status.in_([EnrollmentStatus.ACTIVE,
                                       EnrollmentStatus.PAUSED]))).scalars().all()
    for enrollment in enrollments:
        engine.stop_enrollment(db, enrollment, reason=STOP_REASON, now=now)
    plans = db.execute(select(ReengagementPlan).where(
        ReengagementPlan.lead_id.in_(lead_ids),
        ReengagementPlan.status.in_([reengagement_memory.SCHEDULED,
                                     reengagement_memory.DUE]))).scalars().all()
    for plan in plans:
        reengagement_memory.cancel(db, plan, "the prospect left the company", now=now)
    if not retry or pending or enrollments or plans:
        compliance_audit.record(db, lead=lead, message=None, channel="email",
                                decision=AUDIT_DETECTED, user_id=owner,
                                extra={"move_id": str(move.id), "to_company": move.to_company,
                                       "messages_cancelled": len(pending),
                                       "enrollments_stopped": len(enrollments),
                                       "retry": retry})
    db.commit()
    return {"messages_cancelled": len(pending), "enrollments_stopped": len(enrollments),
            "plans_cancelled": len(plans)}


def _contact_excluded(db: Session, owner, values) -> bool:
    """A CONTACT-kind F05 exclusion on any of the person's old identifiers.
    Contact only: the OLD company being on the customer list is exactly the
    champion case and must not stop anything."""
    from app.db.models import GuardrailExclusion  # noqa: PLC0415
    from app.services import guardrails  # noqa: PLC0415

    keys = {k for k in (guardrails.normalize_contact(v) for v in values if v) if k}
    if not keys:
        return False
    return db.execute(select(GuardrailExclusion.id).where(
        GuardrailExclusion.user_id == owner, GuardrailExclusion.kind == guardrails.CONTACT,
        GuardrailExclusion.removed_at.is_(None),
        GuardrailExclusion.value.in_(sorted(keys))).limit(1)).first() is not None


def _existing_lead(db: Session, owner, old: Lead, person: Person,
                   candidate_email: str | None) -> Lead | None:
    from app.services.guardrails import normalize_company  # noqa: PLC0415

    owned = _owned_lead_ids(owner)
    if candidate_email:
        row = db.execute(select(Lead).where(
            Lead.id.in_(owned), Lead.id != old.id,
            func.lower(Lead.email) == candidate_email.lower())).scalars().first()
        if row is not None:
            return row
    if old.linkedin_url and person.company:
        target = normalize_company(person.company)
        for row in db.execute(select(Lead).where(
                Lead.id.in_(owned), Lead.id != old.id,
                Lead.linkedin_url == old.linkedin_url)).scalars():
            if target and normalize_company(row.company) == target:
                return row
    return None


class _CandidateStep(wf.FinderStep):
    """The address the role check already returned (no extra call, cost 0)."""

    key = STEP_EMAIL

    def __init__(self, email: str | None, provider: str):
        self.email = email
        self.provider = provider

    def find(self, lead: Lead) -> wf.FinderResult:
        return wf.FinderResult(email=self.email, called=False, provider=self.provider)


class _HunterStep(wf.HunterFinderStep):
    key = STEP_HUNTER


def _verifier_available(verifier) -> bool:
    return verifier is not None and bool(getattr(verifier, "api_key", True))


def _find_new_email(db: Session, owner, new: Lead, old: Lead, person: Person, verifier, *,
                    provider: str, now: datetime) -> tuple[str | None, str | None]:
    """F01's waterfall for the new lead. Returns (verdict_or_None, note).
    The old address is never a candidate and never stored."""
    from app.services import provenance  # noqa: PLC0415

    if not _verifier_available(verifier):
        return None, "no email verifier configured - no address looked up"
    if budget_remaining(db, owner, now) < EMAIL_LOOKUP_UNITS:
        return None, "budget cap reached - no address looked up"
    old_email = (old.email or "").strip().lower()
    candidate = person.email if person.email and person.email.lower() != old_email else None
    steps = [_CandidateStep(candidate, provider)]
    hunter = _HunterStep(verifier)
    if hunter.available():
        steps.append(hunter)
    ctx = wf.context_for_lead(db, new)
    try:
        result = wf.run_for_lead(db, new, verifier, ctx, steps, now=now)
    except Exception as exc:  # noqa: BLE001 -- the lead stands without an email
        logger.warning("champion email lookup for lead %s failed: %s", new.id, exc)
        db.rollback()
        return None, "email lookup failed - try again from the lead"
    new = db.get(Lead, new.id)
    if result.verdict == wf.SUPPRESSED:
        new.status = LeadStatus.DROPPED
        new.enrichment_json = {**(new.enrichment_json or {}), "dropped_reason": "suppressed"}
        db.commit()
        return wf.SUPPRESSED, "the new address is on the suppression list"
    if (result.email and result.email.strip().lower() != old_email
            and result.verdict in (wf.VALID, wf.CATCH_ALL, wf.UNKNOWN)):
        # F05: the address the waterfall settled on (Hunter's finder included)
        # gets the same exclusion check the provider's address got.
        from app.services import guardrails  # noqa: PLC0415

        guard_owner = guardrails.active_owner(db, new.strategy_id)
        match = (guardrails.find_match(db, guard_owner, email=result.email)
                 if guard_owner is not None else None)
        if match is not None:
            new.status = LeadStatus.DROPPED
            new.enrichment_json = {**(new.enrichment_json or {}),
                                   "dropped_reason": "excluded",
                                   "excluded_by": str(match.id)}
            db.commit()
            return EXCLUDED, f"the address found at the new company is excluded ({match.reason})"
        new.email = result.email
        wf.store_chain_result(new, result, now)
        new.status = wf.LEAD_STATUS_FOR[result.verdict]
        provenance.record_email_verification(
            db, new, wf.PROVENANCE_STATUS_FOR[result.verdict],
            result.verified.score if result.verified else None, commit=False)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return None, "the new address already belongs to another lead in this campaign"
        return result.verdict, None
    return result.verdict, "no deliverable address found at the new company"


def create_reengagement_lead(db: Session, owner, old: Lead, move: ChampionMove,
                             person: Person, *, source, verifier, cached: bool = False,
                             now: datetime | None = None) -> tuple[str, Lead | None, str | None]:
    """The re-engagement lead at the new company. Returns (outcome, lead, detail).

    Never enrolls, never schedules: the lead waits for a person."""
    from app.services import guardrails, provenance, reengagement_memory  # noqa: PLC0415
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    now = now or _now()
    old_email = (old.email or "").strip().lower()
    new_email = (person.email if person.email and person.email.lower() != old_email
                 else None)

    opted_out = opt_out_reason(db, old)
    if opted_out:
        # The person opted out under the old address. Suppression is keyed by
        # address, so carry it to the new one we were told about.
        if new_email and not is_suppressed(db, email=new_email):
            db.add(SuppressionEntry(email=new_email.lower().strip(),
                                    reason="opt_out_carried_over"))
            db.commit()
        return SUPPRESSED, None, f"person {opted_out}; nothing created"
    if not (person.company or person.domain):
        return NO_COMPANY, None, "the provider gave no new company"

    guard_owner = guardrails.active_owner(db, old.strategy_id)
    if guard_owner is not None:
        if _contact_excluded(db, guard_owner, [old.email, old.phone, old.linkedin_url]):
            return EXCLUDED, None, "the person is on the do-not-contact list"
        match = guardrails.find_match(db, guard_owner, email=new_email,
                                      linkedin=old.linkedin_url or person.linkedin_url,
                                      company=person.company, domains=[person.domain])
        if match is not None:
            return EXCLUDED, None, f"the new company is excluded ({match.reason})"

    existing = _existing_lead(db, owner, old, person, new_email)
    if existing is not None:
        return EXISTING_LEAD, existing, "this person is already a lead at the new company"

    provider = getattr(source, "provider", "lead_source")
    observed = now - timedelta(seconds=settings.cache_ttl_enrichment_seconds) if cached else now
    kind = move.champion_kind
    new = Lead(
        strategy_id=old.strategy_id, source=LEAD_SOURCE, external_id=None,
        full_name=person.full_name or old.full_name, title=person.title,
        company=person.company,
        # Same person, same profile: a LinkedIn opt-out keeps applying.
        linkedin_url=old.linkedin_url or person.linkedin_url,
        # No phone carried over (minimisation): the number may be the old desk.
        phone=None, email=None, status=LeadStatus.ENRICHED,
        enrichment_json={
            "company_domain": person.domain,
            CHAMPION_KEY: {
                "move_id": str(move.id), "previous_lead_id": str(old.id),
                "from_company": old.company, "from_title": old.title,
                "champion_kind": kind, "provider": provider,
                "person_external_id": person.external_id,
                "detected_at": now.isoformat(),
            },
            ROLE_KEY: {"state": CURRENT, "checked_at": now.isoformat(),
                       "observed_at": observed.isoformat(), "source": provider,
                       "last_outcome": CURRENT},
        },
    )
    db.add(new)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return EXISTING_LEAD, None, "a matching lead already exists in this campaign"
    source_tag = provenance.APOLLO if provider == "apollo" else provider
    provenance.record_many(db, new, {field: {"source": source_tag, "value": value,
                                             "detail": "champion tracker job change"}
                                     for field, value in (("full_name", new.full_name),
                                                          ("title", new.title),
                                                          ("company", new.company),
                                                          ("company_domain", person.domain))
                                     if value},
                           observed_at=observed, commit=True)

    verdict, note = _find_new_email(db, owner, new, old, person, verifier,
                                    provider=provider, now=now)
    new = db.get(Lead, new.id)
    if verdict == wf.SUPPRESSED:
        return SUPPRESSED, new, note
    if verdict == EXCLUDED:
        return EXCLUDED, new, note
    reengagement_memory.plan_for_job_change(db, new, owner_id=owner, now=now)
    return LEAD_CREATED, new, note


# --------------------------------------------------------------------------
# Human actions
# --------------------------------------------------------------------------


def confirm(db: Session, lead: Lead, *, actor_id, owner_id, reason: str,
            adopt_title: bool = False, now: datetime | None = None) -> dict:
    """A person confirms the prospect still holds the role. Releases held
    messages (they re-enter every gate)."""
    from app.services import compliance_audit, provenance  # noqa: PLC0415

    now = now or _now()
    if active_move(db, owner_id, lead) is not None:
        raise Refused("This prospect is recorded as having left the company. "
                      "Dismiss the move first if that is wrong.")
    rc = role_check(lead)
    adopted = None
    if adopt_title and rc.get("observed_title"):
        adopted = rc["observed_title"]
        lead.title = adopted[:200]
        provenance.record(db, lead, "title", provenance.MANUAL, value=adopted,
                          detail="confirmed by a person after a champion role check",
                          observed_at=now, commit=False)
    _set_role_check(lead, state=CONFIRMED, checked_at=now, observed_at=now, source="manual",
                    by=str(actor_id) if actor_id else None, reason=reason.strip()[:300],
                    retry_after=None)
    compliance_audit.record(db, lead=lead, message=None, channel="email",
                            decision=AUDIT_CONFIRMED, user_id=owner_id,
                            extra={"reason": reason.strip()[:300],
                                   "actor": str(actor_id) if actor_id else None,
                                   "adopted_title": adopted})
    db.commit()
    return {"released": release_held(db, lead, now), "adopted_title": adopted}


def owned_move(db: Session, owner, move_id) -> ChampionMove | None:
    return db.execute(select(ChampionMove).where(
        ChampionMove.id == move_id, ChampionMove.user_id == owner)).scalars().first()


def dismiss_move(db: Session, move: ChampionMove, *, actor_id, owner_id, reason: str,
                 now: datetime | None = None) -> ChampionMove:
    """A wrong detection. Lifts the block for FUTURE messages; cancelled
    messages and stopped enrollments stay as they are (a stop is final)."""
    from app.services import compliance_audit  # noqa: PLC0415

    now = now or _now()
    if move.dismissed_at is not None:
        raise Refused("This move was already dismissed.")
    move.dismissed_at = now
    move.dismissed_by_user_id = actor_id
    move.dismiss_reason = reason.strip()[:300]
    old = db.get(Lead, move.old_lead_id) if move.old_lead_id else None
    if old is not None:
        _set_role_check(old, state=CONFIRMED, checked_at=now, observed_at=now,
                        source="manual", by=str(actor_id) if actor_id else None,
                        reason=f"move dismissed: {move.dismiss_reason}", retry_after=None)
        compliance_audit.record(db, lead=old, message=None, channel="email",
                                decision=AUDIT_DISMISSED, user_id=owner_id,
                                extra={"move_id": str(move.id), "reason": move.dismiss_reason,
                                       "actor": str(actor_id) if actor_id else None})
    db.commit()
    return move


def erase_for_lead(db: Session, lead_id) -> int:
    """GDPR: scrub the personal parts of any move this lead is part of (the
    caller commits). The row stays as a non-personal tombstone so counts
    survive; the erased lead's identifiers are already suppressed by the
    GDPR delete itself."""
    # A held message of an erased person is cancelled, never released: there is
    # no one left to re-verify and nothing may be looked up about them again.
    cancel_held(db, lead_id, "lead erased (GDPR) - not sent",
                prefixes=send_holds.HOLD_PREFIXES)
    personal = dict(from_company=None, from_title=None, to_company=None, to_title=None,
                    to_domain=None, detail=None)
    # Erasing the OLD lead also drops the old-address hash: the GDPR delete
    # suppresses that address in the same commit, so the block lives on as a
    # suppression. Erasing the NEW lead keeps it -- the old address must stay
    # closed and nothing else would cover it.
    old = db.execute(
        update(ChampionMove).where(ChampionMove.old_lead_id == lead_id)
        .values(**personal, old_email_sha256=None)
        .execution_options(synchronize_session="fetch"))
    new = db.execute(
        update(ChampionMove).where(ChampionMove.new_lead_id == lead_id)
        .values(**personal)
        .execution_options(synchronize_session="fetch"))
    return int(old.rowcount or 0) + int(new.rowcount or 0)


# --------------------------------------------------------------------------
# Sweeps (Celery beat, app/workers/champion_tasks.py)
# --------------------------------------------------------------------------


def _source_available(source) -> bool:
    return source is not None and bool(getattr(source, "api_key", True))


def _due_for_check(lead: Lead, now: datetime) -> bool:
    retry = wf._parse(role_check(lead).get("retry_after"))
    return retry is None or retry <= now


def run_held(db: Session, source, verifier=None, *, now: datetime | None = None,
             limit: int | None = None) -> dict:
    """Leads with held messages: release the ones no longer stale, re-verify
    the rest within the caps. With the flag OFF, every hold is released --
    switching the feature off returns the send path to what it was (the
    departure block, a recorded fact, is untouched). An erased or dropped
    lead's holds are cancelled, never released and never looked up. Moves
    whose follow-through crashed are finished first (retry_pending_moves)."""
    now = now or _now()
    counts = {"held_leads": 0, "released": 0, "checked": 0, "skipped_backoff": 0,
              "budget_exhausted": 0, "moves": 0, "failed": 0, "no_provider": 0,
              "cancelled_inactive": 0, "moves_retried": 0}
    on = enabled(db)
    if on:
        counts["moves_retried"] = retry_pending_moves(db, source, verifier, now=now)
    rows = db.execute(
        select(Message.lead_id, Product.user_id)
        .join(Lead, Lead.id == Message.lead_id)
        .join(Strategy, Strategy.id == Lead.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(*_held_filter()).distinct()
    ).all()
    cap = run_cap(db) if limit is None else limit
    for lead_id, owner in rows:
        counts["held_leads"] += 1
        lead = db.get(Lead, lead_id)
        if lead is None:
            continue
        try:
            inactive = inactive_reason(lead)
            if inactive:
                counts["cancelled_inactive"] += cancel_held(
                    db, lead.id, f"lead {inactive} - not re-verified, not sent")
                db.commit()
                continue
            if not on or staleness_hold(db, lead, now) is None:
                counts["released"] += release_held(db, lead, now)
                continue
            if role_check(lead).get("state") in (TITLE_CHANGED, DISPUTED):
                continue                       # waiting for a person
            if not _due_for_check(lead, now):
                counts["skipped_backoff"] += 1
                continue
            if not _source_available(source):
                counts["no_provider"] += 1
                continue
            if counts["checked"] >= cap:
                continue
            result = reverify(db, lead, source, verifier, trigger="send_hold", now=now)
            counts["checked"] += result["outcome"] not in (BUDGET_EXHAUSTED, "suppressed",
                                                           "already_moved")
            counts["released"] += result.get("released", 0)
            counts["budget_exhausted"] += result["outcome"] == BUDGET_EXHAUSTED
            counts["moves"] += result["outcome"] == LEFT
        except Exception:  # noqa: BLE001 -- one lead never stops the sweep
            counts["failed"] += 1
            logger.exception("champion held re-verification failed for lead %s", lead_id)
            db.rollback()
    return counts


def champion_lead_ids(db: Session, owner) -> set[uuid.UUID]:
    """Past positive repliers and customers of ONE account."""
    owned = _owned_lead_ids(owner)
    ids = set(db.execute(select(InboundReply.lead_id).where(
        InboundReply.lead_id.in_(owned), InboundReply.intent_label == "interested")).scalars())
    ids |= set(db.execute(select(Lead.id).where(
        Lead.id.in_(owned), Lead.status == LeadStatus.CLOSED_WON)).scalars())
    ids |= set(db.execute(select(Deal.lead_id).where(
        Deal.user_id == owner, Deal.stage == DealStage.WON, Deal.lead_id.isnot(None),
        Deal.lead_id.in_(owned))).scalars())
    ids |= set(db.execute(select(Lead.id).where(
        Lead.id.in_(owned), Lead.source == LEAD_SOURCE)).scalars())
    ids.discard(None)
    # Local business mode: imported customers (consumers) are never champions
    # and are never re-checked against a provider.
    from app.services.local_business import CUSTOMER_SOURCE  # noqa: PLC0415

    if ids:
        ids -= set(db.execute(select(Lead.id).where(
            Lead.id.in_(ids), Lead.source == CUSTOMER_SOURCE)).scalars())
    return ids


def refresh_candidates(db: Session, owner, now: datetime | None = None) -> list[Lead]:
    """The account's champions whose role is stale, oldest first."""
    now = now or _now()
    ids = champion_lead_ids(db, owner)
    if not ids:
        return []
    moved = set(db.execute(select(ChampionMove.old_lead_id).where(
        ChampionMove.user_id == owner, ChampionMove.old_lead_id.in_(ids))).scalars())
    # A lead carrying an address some other lead was recorded as having LEFT is
    # already blocked at the chokepoint: re-checking it would only spend.
    blocked_hashes = set(db.execute(select(ChampionMove.old_email_sha256).where(
        ChampionMove.user_id == owner, ChampionMove.dismissed_at.is_(None),
        ChampionMove.old_email_sha256.isnot(None))).scalars())
    limit = timedelta(days=staleness_days(db))
    out: list[tuple[datetime, Lead]] = []
    for lead in db.execute(select(Lead).where(Lead.id.in_(ids - moved))).scalars():
        if inactive_reason(lead) or wf.email_hash(lead.email) in blocked_hashes:
            continue
        if role_check(lead).get("state") in (TITLE_CHANGED, DISPUTED):
            continue                           # waiting for a person
        observed = role_observed_at(lead)
        if observed is not None and now - observed <= limit:
            continue
        if (not _due_for_check(lead, now) or _person_suppressed(db, lead)
                or derived_opt_out(db, lead, owner)):
            continue
        out.append((observed or datetime.min.replace(tzinfo=timezone.utc), lead))
    out.sort(key=lambda item: (item[0], str(item[1].id)))
    return [lead for _, lead in out]


def run_refresh(db: Session, source, verifier=None, *, now: datetime | None = None) -> dict:
    """The scheduled champion refresh. Owner by owner, oldest role first,
    within the per-run cap and each account's rolling 30-day unit cap.
    Idempotent: a checked lead is fresh for `champion_staleness_days`."""
    now = now or _now()
    counts = {"accounts": 0, "candidates": 0, "checked": 0, "budget_exhausted": 0,
              "moves": 0, "failed": 0}
    if not enabled(db):
        return {**counts, "skipped": "flag off"}
    if not _source_available(source):
        return {**counts, "skipped": "no lead source credentials"}
    cap = run_cap(db)
    owners = sorted(set(db.execute(select(Product.user_id).join(
        Strategy, Strategy.product_id == Product.id)).scalars()), key=str)
    for owner in owners:
        if counts["checked"] >= cap:
            break
        candidates = refresh_candidates(db, owner, now)
        if not candidates:
            continue
        counts["accounts"] += 1
        counts["candidates"] += len(candidates)
        for lead in candidates:
            if counts["checked"] >= cap:
                break
            if budget_remaining(db, owner, now) < ROLE_CHECK_UNITS:
                counts["budget_exhausted"] += 1
                break                          # this account is done for the window
            try:
                result = reverify(db, lead, source, verifier, trigger="refresh", now=now)
            except Exception:  # noqa: BLE001
                counts["failed"] += 1
                logger.exception("champion refresh failed for lead %s", lead.id)
                db.rollback()
                continue
            counts["checked"] += 1
            counts["moves"] += result["outcome"] == LEFT
    return counts


# --------------------------------------------------------------------------
# Output (every function takes the owning user id)
# --------------------------------------------------------------------------


def move_out(db: Session, move: ChampionMove) -> dict:
    new = db.get(Lead, move.new_lead_id) if move.new_lead_id else None
    return {
        "id": str(move.id),
        "old_lead_id": str(move.old_lead_id) if move.old_lead_id else None,
        "new_lead_id": str(move.new_lead_id) if move.new_lead_id else None,
        "new_lead": ({"id": str(new.id), "full_name": new.full_name, "title": new.title,
                      "company": new.company, "email": new.email,
                      "status": new.status.value if new.status else None} if new else None),
        "champion_kind": move.champion_kind,
        "from_company": move.from_company, "from_title": move.from_title,
        "to_company": move.to_company, "to_title": move.to_title, "to_domain": move.to_domain,
        "trigger": move.trigger, "outcome": move.outcome, "detail": move.detail,
        "detected_at": move.detected_at.isoformat() if move.detected_at else None,
        "dismissed_at": move.dismissed_at.isoformat() if move.dismissed_at else None,
        "dismiss_reason": move.dismiss_reason,
    }


def list_moves(db: Session, owner, *, limit: int = 50, offset: int = 0) -> dict:
    total = db.execute(select(func.count(ChampionMove.id)).where(
        ChampionMove.user_id == owner)).scalar_one()
    rows = db.execute(select(ChampionMove).where(ChampionMove.user_id == owner)
                      .order_by(ChampionMove.detected_at.desc(), ChampionMove.id)
                      .offset(offset).limit(limit)).scalars().all()
    return {"total": int(total), "limit": limit, "offset": offset,
            "items": [move_out(db, row) for row in rows]}


def _message_out(message: Message, lead: Lead | None = None) -> dict:
    out = {"id": str(message.id), "lead_id": str(message.lead_id),
           "channel": message.channel.value if message.channel else None,
           "step_no": message.step_no, "status": message.status.value,
           "reason": (message.error or "").removeprefix(ERROR_PREFIX) or None,
           "scheduled_at": message.scheduled_at.isoformat() if message.scheduled_at else None}
    if lead is not None:
        out["lead"] = {"full_name": lead.full_name, "title": lead.title, "company": lead.company}
    return out


def held_list(db: Session, owner, *, limit: int = 100) -> dict:
    rows = db.execute(
        select(Message, Lead).join(Lead, Lead.id == Message.lead_id)
        .where(Message.lead_id.in_(_owned_lead_ids(owner)), *_held_filter())
        .order_by(Message.scheduled_at, Message.id).limit(limit)).all()
    total = db.execute(select(func.count(Message.id)).where(
        Message.lead_id.in_(_owned_lead_ids(owner)), *_held_filter())).scalar_one()
    return {"total": int(total), "items": [_message_out(m, lead) for m, lead in rows]}


def attempts_for_lead(db: Session, owner, lead: Lead, limit: int = 20) -> list[dict]:
    rows = db.execute(
        select(EnrichmentAttempt)
        .where(EnrichmentAttempt.user_id == owner, EnrichmentAttempt.lead_id == lead.id,
               EnrichmentAttempt.step.like(f"{LEDGER_PREFIX}%"))
        .order_by(EnrichmentAttempt.created_at.desc(), EnrichmentAttempt.id).limit(limit)
    ).scalars().all()
    return [{"id": str(r.id), "step": r.step, "provider": r.provider, "operation": r.operation,
             "outcome": r.outcome, "cached": bool(r.cached), "cost_units": r.cost_units,
             "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]


def role_check_out(db: Session, lead: Lead, owner, now: datetime | None = None) -> dict:
    now = now or _now()
    rc = role_check(lead)
    observed = role_observed_at(lead)
    on = enabled(db)
    move = active_move(db, owner, lead)
    any_move = move or db.execute(select(ChampionMove).where(
        ChampionMove.user_id == owner, ChampionMove.old_lead_id == lead.id)).scalars().first()
    hold = staleness_hold(db, lead, now)
    held = held_messages(db, lead)
    if move is not None:
        decision = {"would_send": False, "blocked": True, "held": False,
                    "reason": f"left {move.from_company or 'the company'} - the old address "
                              f"is closed"}
    else:
        decision = {"would_send": not (on and hold), "blocked": False,
                    "held": bool(on and hold), "reason": hold if on else None,
                    "would_hold_if_enabled": hold}
    info = champion_info(lead)
    return {
        "lead_id": str(lead.id),
        "enabled": on,
        "title": lead.title, "company": lead.company,
        "state": rc.get("state"),
        "last_outcome": rc.get("last_outcome"),
        "observed_title": rc.get("observed_title"),
        "observed_company": rc.get("observed_company"),
        "checked_at": rc.get("checked_at"),
        "attempted_at": rc.get("attempted_at"),
        "retry_after": rc.get("retry_after"),
        "confirmed_by": rc.get("by") if rc.get("state") == CONFIRMED else None,
        "observed_at": observed.isoformat() if observed else None,
        "age_days": max(0, (now - observed).days) if observed else None,
        "champion_kind": champion_kind(db, lead, owner),
        "previous": ({k: info.get(k) for k in ("from_company", "from_title", "previous_lead_id",
                                              "move_id")} if info else None),
        "send_decision": decision,
        "held_messages": [_message_out(m) for m in held],
        "move": move_out(db, any_move) if any_move is not None else None,
        "attempts": attempts_for_lead(db, owner, lead),
        "settings": settings_out(db),
    }


def metrics(db: Session, owner, *, days: int = 90, now: datetime | None = None) -> dict:
    """The F10 success metric: sends after a confirmed departure (target 0)
    and champion re-engagements. Measured from rows, never estimated."""
    now = now or _now()
    since = now - timedelta(days=days)
    moves = db.execute(select(ChampionMove).where(
        ChampionMove.user_id == owner)).scalars().all()
    in_window = [m for m in moves if _aware(m.detected_at) >= since]
    by_outcome = {key: 0 for key in OUTCOMES}
    for move in in_window:
        by_outcome[move.outcome] = by_outcome.get(move.outcome, 0) + 1

    reengaged = [m for m in in_window if m.outcome == LEAD_CREATED and m.new_lead_id]
    statuses = [db.get(Lead, m.new_lead_id) for m in reengaged]
    statuses = [lead.status for lead in statuses if lead is not None]

    # Sends after departure, all-time, un-dismissed moves, the old lead AND
    # every lead of the account with the same address.
    sends_after = 0
    for move in moves:
        if move.dismissed_at is not None:
            continue
        ids = {move.old_lead_id} - {None}
        old = db.get(Lead, move.old_lead_id) if move.old_lead_id else None
        if old is not None and old.email:
            ids |= set(_same_address_lead_ids(db, owner, old.email))
        if not ids:
            continue
        sends_after += int(db.execute(
            select(func.count(Outcome.id)).join(Message, Message.id == Outcome.message_id)
            .where(Outcome.event == OutcomeEvent.SENT, Message.lead_id.in_(ids),
                   Message.sent_at > move.detected_at)).scalar_one())

    return {
        "window_days": days,
        "moves_detected": len(in_window),
        "by_outcome": by_outcome,
        "champion_reengagements": len(reengaged),
        "reengagement_progress": {
            "contacted": sum(1 for s in statuses if s in _CONTACTED),
            "replied": sum(1 for s in statuses if s in _REPLIED),
            "meeting_booked": sum(1 for s in statuses if s in _MEETING),
        },
        "sends_after_departure": sends_after,
        "target_sends_after_departure": 0,
        "held_now": held_list(db, owner, limit=1)["total"],
        "budget": {"units_used_30d": units_used(db, owner, now),
                   "account_monthly_units": account_units_cap(db),
                   "run_cap": run_cap(db)},
        "settings": settings_out(db),
    }
