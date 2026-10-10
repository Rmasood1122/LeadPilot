"""F01 -- Bounce Shield: a SAFETY GUARD in the send chokepoint.

With `bounce_shield_enabled` on, an EMAIL send proceeds only if the lead's
current address is verified-valid (fresh), or catch-all under an `allow`
policy, or a manager overrode the block for that lead. Anything else is
blocked inside app/workers/outreach_tasks.py::send_message_impl, right after
the suppression check -- before a claim, a render, a model call or a cap slot.

WHAT IT NEVER DOES
- It never sends. It only removes sends. A blocked message re-queued after an
  override or a re-verification goes back through send_message_impl and every
  gate in it (suppression, consent rules, window, caps, mailbox health, client
  domain isolation, the review queue).
- An override never reaches an address verified undeliverable, a suppressed
  address, or a lead with no address.
- It does not touch any bounce threshold. The campaign auto-pause (3%,
  sequence_engine.check_bounce_rate) and mailbox health (2% / 5%) are
  unchanged; F01's "< 2% on verified sends" is a MEASUREMENT reported by
  metrics(), not a brake. See docs/features/f01-waterfall-enrichment.md.

Off = no behaviour change: the send path does not even read a lead's verdict.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    ChannelType,
    EnrichmentAttempt,
    Lead,
    Message,
    MessageStatus,
    Outcome,
    OutcomeEvent,
    Product,
    Strategy,
)
from app.services import waterfall_enrichment as wf

logger = logging.getLogger(__name__)

FLAG = "bounce_shield_enabled"
POLICY_SETTING = "bounce_shield_catch_all_policy"
MAX_AGE_SETTING = "bounce_shield_max_age_days"

POLICY_BLOCK = "block"
POLICY_ALLOW = "allow"

# message.error prefix for a shield block. The requeue matches on it, so it is
# a contract: change it and blocked messages can no longer be released.
ERROR_PREFIX = "bounce_shield: "
SEND_RESULT = "blocked_unverified_email"
AUDIT_BLOCKED = "blocked_unverified_email"
AUDIT_OVERRIDE = "bounce_shield_override"
AUDIT_OVERRIDE_REVOKED = "bounce_shield_override_revoked"

OVERRIDE_KEY = "bounce_shield_override"

# The F01 success metric. A measurement target, NOT a threshold anything acts on.
TARGET_VERIFIED_BOUNCE_RATE = 0.02
# Below this many verified sends the measured rate is reported but flagged.
MIN_SAMPLE_SENDS = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enabled(db: Session) -> bool:
    from app.services import system_settings  # noqa: PLC0415

    return bool(system_settings.get(db, FLAG))


def catch_all_policy(db: Session) -> str:
    """'allow' only when it says exactly that; anything else fails closed."""
    from app.services import system_settings  # noqa: PLC0415

    value = str(system_settings.get(db, POLICY_SETTING) or "").strip().lower()
    return POLICY_ALLOW if value == POLICY_ALLOW else POLICY_BLOCK


def max_age_days(db: Session) -> int:
    from app.services import system_settings  # noqa: PLC0415

    return int(system_settings.get(db, MAX_AGE_SETTING))


def settings_out(db: Session) -> dict:
    return {"enabled": enabled(db), "waterfall_enabled": wf.enabled(db),
            "catch_all_policy": catch_all_policy(db), "max_age_days": max_age_days(db)}


# --------------------------------------------------------------------------
# The decision
# --------------------------------------------------------------------------


@dataclass
class Decision:
    allowed: bool
    tag: str | None = None          # valid | catch_all | override (SENT meta)
    reason: str | None = None       # why not, in words a user can act on
    verdict: str | None = None      # the verdict on record for this address


def override_for(lead: Lead) -> dict | None:
    """The override, only if it was given for the lead's CURRENT address."""
    stored = lead.enrichment_json if isinstance(lead.enrichment_json, dict) else {}
    override = stored.get(OVERRIDE_KEY)
    if not isinstance(override, dict) or not lead.email:
        return None
    return override if override.get("email_sha256") == wf.email_hash(lead.email) else None


def decide(db: Session, lead: Lead, now: datetime | None = None) -> Decision:
    """May an email go to this lead's current address? Pure read."""
    now = now or _now()
    if not (lead.email or "").strip():
        return Decision(False, reason="no email address on file")

    record = wf.verdict_for(lead)
    verdict = record["verdict"] if record else None
    if verdict == wf.INVALID:
        return Decision(False, reason="the address was verified undeliverable",
                        verdict=verdict)

    limit = max_age_days(db)
    checked = wf._parse(record.get("checked_at")) if record else None
    fresh = checked is not None and now - checked <= timedelta(days=limit)

    if fresh and verdict == wf.VALID:
        return Decision(True, tag=wf.VALID, verdict=verdict)
    policy = catch_all_policy(db)
    if fresh and verdict == wf.CATCH_ALL and policy == POLICY_ALLOW:
        return Decision(True, tag=wf.CATCH_ALL, verdict=verdict)
    if override_for(lead) is not None:
        return Decision(True, tag="override", verdict=verdict)

    if record is None:
        if wf.verdict_record(lead) is not None:
            reason = "the address changed after it was verified - re-verify it"
        else:
            reason = "no verification on record for this address - re-verify or override"
    elif not fresh:
        reason = f"the verification is older than {limit} days - re-verify it"
    elif verdict == wf.CATCH_ALL:
        reason = "catch-all domain (policy: block) - override to send"
    else:
        reason = "the verifier could not confirm the address (unknown) - override to send"
    return Decision(False, reason=reason, verdict=verdict)


def block_message(db: Session, message: Message, decision: Decision) -> None:
    """Mark a message blocked (the caller writes the audit row and commits).
    FAILED with the shield prefix: kept, visible, and releasable."""
    message.status = MessageStatus.FAILED
    message.error = f"{ERROR_PREFIX}{decision.reason}"[:1000]


def requeue_blocked(db: Session, lead: Lead, now: datetime | None = None) -> int:
    """Return this lead's shield-blocked messages to SCHEDULED, due now. They
    are re-checked by the full send path; this is not a bypass."""
    from app.services import send_holds  # noqa: PLC0415

    # At most one message per (sequence, step); extra held copies are
    # cancelled -- see app/services/send_holds.py.
    return send_holds.release(db, lead.id, ERROR_PREFIX, now or _now())


# --------------------------------------------------------------------------
# Override
# --------------------------------------------------------------------------


class OverrideRefused(ValueError):
    pass


def set_override(db: Session, lead: Lead, *, actor_id, owner_id, reason: str,
                 now: datetime | None = None) -> dict:
    from app.services import compliance_audit  # noqa: PLC0415
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    now = now or _now()
    if not (lead.email or "").strip():
        raise OverrideRefused("This prospect has no email address.")
    if is_suppressed(db, email=lead.email, phone=lead.phone, linkedin=lead.linkedin_url):
        raise OverrideRefused("This prospect is on the suppression list.")
    record = wf.verdict_for(lead)
    if record is not None and record["verdict"] == wf.INVALID:
        raise OverrideRefused("The address was verified undeliverable; an override "
                              "cannot make it deliverable.")
    override = {
        "by": str(actor_id) if actor_id else None,
        "at": now.isoformat(),
        "reason": reason.strip()[:300],
        "email_sha256": wf.email_hash(lead.email),
        "verdict_at_override": record["verdict"] if record else None,
    }
    lead.enrichment_json = {**(lead.enrichment_json or {}), OVERRIDE_KEY: override}
    compliance_audit.record(db, lead=lead, message=None, channel="email",
                            decision=AUDIT_OVERRIDE, user_id=owner_id,
                            extra={"reason": override["reason"], "actor": override["by"],
                                   "verdict": override["verdict_at_override"]})
    db.commit()
    return override


def clear_override(db: Session, lead: Lead, *, actor_id, owner_id, why: str) -> bool:
    from app.services import compliance_audit  # noqa: PLC0415

    stored = dict(lead.enrichment_json or {})
    if OVERRIDE_KEY not in stored:
        return False
    stored.pop(OVERRIDE_KEY)
    lead.enrichment_json = stored
    compliance_audit.record(db, lead=lead, message=None, channel="email",
                            decision=AUDIT_OVERRIDE_REVOKED, user_id=owner_id,
                            extra={"actor": str(actor_id) if actor_id else None, "why": why})
    db.commit()
    return True


def refresh(db: Session, lead: Lead, verifier, *, actor_id, owner_id,
            now: datetime | None = None) -> dict:
    """Re-verify the lead's current address (the 30-day provider cache still
    applies). Never changes lead.status or the address; an `invalid` answer
    removes any override. Returns the new verdict record."""
    from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

    now = now or _now()
    if not (lead.email or "").strip():
        raise OverrideRefused("This prospect has no email address.")
    if is_suppressed(db, email=lead.email):
        raise OverrideRefused("This prospect is on the suppression list.")
    ctx = wf.context_for_lead(db, lead)
    verified = wf.verify_address(db, lead, lead.email, verifier, ctx, step="reverify",
                                 now=now, reuse=False)
    previous = wf.verdict_record(lead)
    record = wf.store_verdict(
        lead, verdict=verified.verdict, email=lead.email,
        provider=(previous or {}).get("provider") or lead.source,
        verifier=verified.verifier, score=verified.score,
        legacy_status=verified.legacy_status, checked_at=now)
    db.commit()
    if verified.verdict == wf.INVALID:
        clear_override(db, lead, actor_id=actor_id, owner_id=owner_id,
                       why="re-verification found the address undeliverable")
    return {**record, "cached": verified.cached}


# --------------------------------------------------------------------------
# Measurement (the F01 success metric) -- owner-scoped
# --------------------------------------------------------------------------


def _owned_lead_ids(user_id):
    return (select(Lead.id).join(Strategy, Strategy.id == Lead.strategy_id)
            .join(Product, Product.id == Strategy.product_id)
            .where(Product.user_id == user_id))


def metrics(db: Session, user_id: uuid.UUID, *, days: int = 30,
            now: datetime | None = None, verifier=None) -> dict:
    """Bounces on email sends in the window, split by the verdict tag the
    send carried. The F01 number is `verified_send_bounce_rate`.

    Bounces are every BOUNCED outcome on those messages. The bounce path does
    not distinguish hard from soft, so this is an UPPER BOUND on the
    hard-bounce rate (see the spec's Unverified section)."""
    now = now or _now()
    since = now - timedelta(days=days)
    owned = _owned_lead_ids(user_id)

    sent_rows = db.execute(
        select(Outcome.message_id, Outcome.meta_json)
        .join(Message, Message.id == Outcome.message_id)
        .where(Outcome.event == OutcomeEvent.SENT,
               Message.channel == ChannelType.EMAIL,
               Message.lead_id.in_(owned),
               Message.sent_at >= since)
    ).all()
    tag_of: dict = {}
    for message_id, meta in sent_rows:
        tag = (meta or {}).get("email_verdict") if isinstance(meta, dict) else None
        tag_of[message_id] = tag if tag in (wf.VALID, wf.CATCH_ALL, "override") else "untagged"

    bounced: set = set()
    if tag_of:
        bounced = set(db.execute(
            select(Outcome.message_id)
            .where(Outcome.event == OutcomeEvent.BOUNCED,
                   Outcome.lead_id.in_(owned),
                   Outcome.message_id.in_(list(tag_of)))
        ).scalars())

    by_tag = {}
    for tag in (wf.VALID, wf.CATCH_ALL, "override", "untagged"):
        ids = [m for m, t in tag_of.items() if t == tag]
        hits = sum(1 for m in ids if m in bounced)
        by_tag[tag] = {"sent": len(ids), "bounced": hits,
                       "rate": round(hits / len(ids), 4) if ids else None}

    verified = by_tag[wf.VALID]
    attempts = db.execute(
        select(EnrichmentAttempt).where(EnrichmentAttempt.user_id == user_id,
                                        EnrichmentAttempt.created_at >= since)
    ).scalars().all()
    by_provider: dict = {}
    verdicts: dict = {}
    for row in attempts:
        bucket = by_provider.setdefault(row.provider, {"attempts": 0, "paid": 0, "cached": 0,
                                                       "cost_units": 0})
        bucket["attempts"] += 1
        bucket["cached"] += int(bool(row.cached))
        bucket["paid"] += int(row.cost_units > 0)
        bucket["cost_units"] += row.cost_units
        if row.operation == "verify" and row.outcome in wf.VERDICTS:
            verdicts[row.outcome] = verdicts.get(row.outcome, 0) + 1

    out = {
        "window_days": days,
        "target_verified_bounce_rate": TARGET_VERIFIED_BOUNCE_RATE,
        "verified_send_bounce_rate": verified["rate"],
        "verified_sends": verified["sent"],
        "sample_ok": verified["sent"] >= MIN_SAMPLE_SENDS,
        "bounces_counted": "every recorded email bounce (hard and soft are not "
                           "distinguished) - an upper bound on hard bounces",
        "sends": by_tag,
        "campaign_pause_threshold": settings.bounce_rate_pause_threshold,
        "ledger": {
            "attempts": len(attempts),
            "paid_attempts": sum(b["paid"] for b in by_provider.values()),
            "cached_attempts": sum(b["cached"] for b in by_provider.values()),
            "cost_units": sum(b["cost_units"] for b in by_provider.values()),
            "by_provider": by_provider,
            "verdicts": verdicts,
        },
        "settings": settings_out(db),
    }
    if verifier is not None:
        out["providers"] = wf.provider_status(db, verifier)
    return out


def attempts_for_lead(db: Session, user_id: uuid.UUID, lead: Lead, limit: int = 50) -> list[dict]:
    rows = db.execute(
        select(EnrichmentAttempt)
        .where(EnrichmentAttempt.user_id == user_id, EnrichmentAttempt.lead_id == lead.id)
        .order_by(EnrichmentAttempt.created_at.desc(), EnrichmentAttempt.id)
        .limit(limit)
    ).scalars().all()
    return [{"id": str(r.id), "step": r.step, "provider": r.provider,
             "operation": r.operation, "outcome": r.outcome, "cached": bool(r.cached),
             "cost_units": r.cost_units, "claimed_status": r.claimed_status,
             "email_domain": r.email_domain,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]
