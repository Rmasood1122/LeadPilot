"""Lead pipeline — the sourcing chain as Celery tasks.

Chain per batch:  source_leads -> enrich_leads -> find_missing_emails
                  -> verify_emails -> finalize_lead_batch

Guarantees (mirroring the M1 engine's resumability rule):
- Idempotent: every stage selects work by lead status, and dedupe is
  enforced both in code and by the DB's unique constraints — re-running a
  stage never duplicates a lead.
- Resumable: each lead commits individually as it advances; a crashed
  stage re-runs and continues with whatever leads are still behind.
- Suppression list is checked at sourcing time AND again whenever a new
  email/phone is discovered. No exceptions — compliance rule.

Each task body is a plain `_impl` function taking a Session, so the test
suite exercises the real logic with SQLite + fake adapters and zero
broker/API usage.
"""

import logging
import uuid

from celery import chain
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.base import SessionLocal
from app.db.models import BatchStage, Lead, LeadBatch, LeadStatus, SuppressionEntry
from app.integrations.base import (
    EmailVerifier,
    LeadSource,
    RawLead,
    get_email_verifier,
    get_lead_source,
)

# Importing the adapter modules registers them.
import app.integrations.apollo  # noqa: F401
import app.integrations.hunter  # noqa: F401

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Provider factories (tests monkeypatch these two functions)
# --------------------------------------------------------------------------


def _get_source(batch: LeadBatch) -> LeadSource:
    return get_lead_source(batch.source_provider or settings.lead_source_provider)


def _get_verifier(batch: LeadBatch) -> EmailVerifier:
    return get_email_verifier(batch.verifier_provider or settings.email_verifier_provider)


# --------------------------------------------------------------------------
# Suppression — always checked, no exceptions
# --------------------------------------------------------------------------


def is_suppressed(session: Session, email: str | None = None, phone: str | None = None,
                  linkedin: str | None = None) -> bool:
    """True if ANY of the contact's identifiers is suppressed.

    Feature Group 5 added `linkedin` (a profile URL or slug), checked against
    linkedin_suppressions. Every send path passes all three, so a person who
    opted out on one channel is never reached on another.
    """
    if email or phone:
        conditions = []
        if email:
            conditions.append(SuppressionEntry.email == email.lower().strip())
        if phone:
            conditions.append(SuppressionEntry.phone == phone.strip())
        row = session.execute(
            select(SuppressionEntry.id).where(or_(*conditions)).limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return True
    if linkedin:
        from app.db.models import LinkedInSuppression  # noqa: PLC0415
        from app.services.linkedin_outreach import normalize_profile  # noqa: PLC0415

        profile = normalize_profile(linkedin)
        if profile and session.execute(
            select(LinkedInSuppression.id).where(LinkedInSuppression.profile == profile)
        ).scalar_one_or_none() is not None:
            return True
    return False


# --------------------------------------------------------------------------
# Stage implementations
# --------------------------------------------------------------------------


def _set_stage(session: Session, batch: LeadBatch, stage: BatchStage) -> None:
    batch.stage = stage
    session.commit()


def _lead_exists(session: Session, batch: LeadBatch, raw: RawLead) -> bool:
    conditions = []
    if raw.email:
        conditions.append(Lead.email == raw.email)
    if raw.external_id:
        conditions.append((Lead.source == raw.source) & (Lead.external_id == raw.external_id))
    if not conditions:
        return False
    row = session.execute(
        select(Lead.id)
        .where(Lead.strategy_id == batch.strategy_id, or_(*conditions))
        .limit(1)
    ).scalar_one_or_none()
    return row is not None


def _linkedin_url(payload: dict | None) -> str | None:
    """Feature Group 2/5: the profile URL Apollo reports (top level on search
    rows, person.linkedin_url on enrichment)."""
    from app.services.personalization_context import linkedin_url_from  # noqa: PLC0415

    return linkedin_url_from(payload)


def source_leads_impl(session: Session, batch_id: uuid.UUID, source: LeadSource | None = None) -> dict:
    batch = session.get(LeadBatch, batch_id)
    _set_stage(session, batch, BatchStage.SOURCING)
    source = source or _get_source(batch)

    raw_leads = source.search(batch.icp_criteria_json or {}, batch.requested_leads)

    added = skipped_duplicate = skipped_suppressed = 0
    for raw in raw_leads:
        if is_suppressed(session, raw.email, raw.phone):
            skipped_suppressed += 1
            continue
        if _lead_exists(session, batch, raw):
            skipped_duplicate += 1
            continue
        session.add(Lead(
            strategy_id=batch.strategy_id,
            batch_id=batch.id,
            source=raw.source,
            external_id=raw.external_id,
            full_name=raw.full_name,
            title=raw.title,
            company=raw.company,
            email=raw.email,
            phone=raw.phone,
            enrichment_json={"raw": raw.raw, "company_domain": raw.company_domain},
            status=LeadStatus.SOURCED,
            linkedin_url=_linkedin_url(raw.raw),
        ))
        try:
            session.commit()  # per-lead commit: crash-safe, resume-safe
            added += 1
        except IntegrityError:
            session.rollback()  # racing worker inserted it — schema-level dedupe
            skipped_duplicate += 1

    counts = {"added": added, "duplicates": skipped_duplicate, "suppressed": skipped_suppressed}
    logger.info("batch %s sourced: %s", batch_id, counts)
    return counts


def enrich_leads_impl(session: Session, batch_id: uuid.UUID, source: LeadSource | None = None) -> int:
    batch = session.get(LeadBatch, batch_id)
    _set_stage(session, batch, BatchStage.ENRICHING)
    source = source or _get_source(batch)

    leads = session.execute(
        select(Lead).where(Lead.batch_id == batch_id, Lead.status == LeadStatus.SOURCED)
    ).scalars().all()

    processed = 0
    for lead in leads:
        stored = lead.enrichment_json or {}
        raw = RawLead(
            source=lead.source,
            external_id=lead.external_id,
            full_name=lead.full_name,
            title=lead.title,
            company=lead.company,
            company_domain=stored.get("company_domain"),
            email=lead.email,
            phone=lead.phone,
            raw=stored.get("raw") or {},
        )
        enriched = source.enrich(raw)

        new_email = lead.email or enriched.email
        new_phone = lead.phone or enriched.phone
        if is_suppressed(session, new_email, new_phone):
            lead.status = LeadStatus.DROPPED
            lead.enrichment_json = {**stored, "dropped_reason": "suppressed"}
        else:
            lead.email = new_email
            lead.phone = new_phone
            lead.full_name = lead.full_name or enriched.full_name
            lead.title = lead.title or enriched.title
            lead.company = lead.company or enriched.company
            lead.linkedin_url = lead.linkedin_url or _linkedin_url(enriched.enrichment)
            lead.enrichment_json = {
                **stored,
                "company_domain": enriched.company_domain or stored.get("company_domain"),
                "enrichment": enriched.enrichment,
            }
            lead.status = LeadStatus.ENRICHED
        try:
            session.commit()  # per-lead: resume continues from here
        except IntegrityError:
            # enrichment surfaced an email another lead already owns
            session.rollback()
            lead.email = None
            lead.status = LeadStatus.ENRICHED
            session.commit()
        processed += 1
    return processed


def find_missing_emails_impl(
    session: Session, batch_id: uuid.UUID, verifier: EmailVerifier | None = None
) -> dict:
    batch = session.get(LeadBatch, batch_id)
    _set_stage(session, batch, BatchStage.FINDING_EMAILS)
    verifier = verifier or _get_verifier(batch)

    leads = session.execute(
        select(Lead).where(Lead.batch_id == batch_id, Lead.status == LeadStatus.ENRICHED)
    ).scalars().all()

    found = already_had = dropped = 0
    for lead in leads:
        if lead.email:
            lead.status = LeadStatus.EMAIL_FOUND
            session.commit()
            already_had += 1
            continue

        domain = (lead.enrichment_json or {}).get("company_domain")
        email = verifier.find_email(lead.full_name or "", domain or "") if domain else None

        if not email or is_suppressed(session, email=email):
            lead.status = LeadStatus.DROPPED
            lead.enrichment_json = {
                **(lead.enrichment_json or {}),
                "dropped_reason": "no_email_found" if not email else "suppressed",
            }
            session.commit()
            dropped += 1
            continue

        lead.email = email
        lead.status = LeadStatus.EMAIL_FOUND
        try:
            session.commit()
            found += 1
        except IntegrityError:  # duplicate email within the strategy
            session.rollback()
            lead.email = None
            lead.status = LeadStatus.DROPPED
            lead.enrichment_json = {**(lead.enrichment_json or {}), "dropped_reason": "duplicate_email"}
            session.commit()
            dropped += 1

    return {"found": found, "already_had": already_had, "dropped": dropped}


def verify_emails_impl(
    session: Session, batch_id: uuid.UUID, verifier: EmailVerifier | None = None
) -> dict:
    batch = session.get(LeadBatch, batch_id)
    _set_stage(session, batch, BatchStage.VERIFYING)
    verifier = verifier or _get_verifier(batch)

    leads = session.execute(
        select(Lead).where(Lead.batch_id == batch_id, Lead.status == LeadStatus.EMAIL_FOUND)
    ).scalars().all()

    counts = {"verified": 0, "flagged": 0, "dropped": 0}
    for lead in leads:
        result = verifier.verify(lead.email)
        lead.status = result.lead_status
        lead.enrichment_json = {
            **(lead.enrichment_json or {}),
            "verification": {"status": result.status.value, "score": result.score},
        }
        session.commit()  # per-lead: resume-safe
        if lead.status is LeadStatus.VERIFIED:
            counts["verified"] += 1
        elif lead.status is LeadStatus.FLAGGED:
            counts["flagged"] += 1
        else:
            counts["dropped"] += 1
    return counts


def finalize_lead_batch_impl(session: Session, batch_id: uuid.UUID) -> dict:
    batch = session.get(LeadBatch, batch_id)
    rows = session.execute(select(Lead.status).where(Lead.batch_id == batch_id)).scalars().all()
    summary = {status.value: 0 for status in LeadStatus}
    for s in rows:
        summary[s.value] += 1
    batch.summary_json = {"counts": summary, "total": len(rows)}
    batch.stage = BatchStage.FINALIZED
    session.commit()
    logger.info("batch %s finalized: %s", batch_id, batch.summary_json)

    # Feature Group 1: score the leads that survived verification. After the
    # FINALIZED commit on purpose -- sourcing has succeeded whatever happens
    # next, and score_batch never raises (a model failure falls back to the
    # heuristic score).
    from app.db.models import Strategy as _Strategy  # noqa: PLC0415
    from app.services import lead_scoring, usage_meter  # noqa: PLC0415

    strategy = session.get(_Strategy, batch.strategy_id) if batch else None
    with usage_meter.owner_scope(session, strategy, "lead_scoring"):
        scored = lead_scoring.score_batch(session, batch_id)
    if scored:
        logger.info("batch %s: scored %d leads", batch_id, scored)
    _emit_lead_sourced(session, batch)
    return batch.summary_json


def _emit_lead_sourced(session: Session, batch: LeadBatch) -> None:
    """Feature Group 4: `lead_sourced` to outbound webhooks (Zapier / Make),
    carrying the batch's verified leads (first 200). Webhook-only -- a push
    per sourcing batch would be noise. Never raises: sourcing has succeeded."""
    from app.db.models import Strategy as _Strategy  # noqa: PLC0415
    from app.services import event_bus, notifications  # noqa: PLC0415
    from app.workers import notification_tasks  # noqa: PLC0415

    try:
        strategy = session.get(_Strategy, batch.strategy_id)
        owner = notifications.owner_of_strategy(session, strategy) if strategy else None
        if owner is None:
            return
        leads = session.execute(
            select(Lead).where(Lead.batch_id == batch.id, Lead.status == LeadStatus.VERIFIED)
            .limit(200)
        ).scalars().all()
        if not leads:
            return
        notification_tasks.enqueue_event(
            owner, "lead_sourced", push=False, slack=False,
            title=f"{len(leads)} leads sourced", body="A sourcing batch finished.",
            deep_link="/pipeline",
            data={"batchId": str(batch.id), "strategyId": str(batch.strategy_id)},
            webhook_payload={"batch_id": str(batch.id), "strategy_id": str(batch.strategy_id),
                             "counts": (batch.summary_json or {}).get("counts", {}),
                             "leads": [event_bus.lead_payload(lead) for lead in leads]},
        )
    except Exception:
        logger.exception("batch %s: lead_sourced event failed", batch.id)


# --------------------------------------------------------------------------
# Celery task wrappers + the chain
# --------------------------------------------------------------------------


def _run_stage(impl, batch_id: str, task) -> dict | int:
    session = SessionLocal()
    try:
        return impl(session, uuid.UUID(batch_id))
    except Exception as exc:
        session.rollback()
        batch = session.get(LeadBatch, uuid.UUID(batch_id))
        if batch is not None:
            batch.error = f"{type(exc).__name__}: {exc}"
            session.commit()
        logger.exception("lead stage failed for batch %s — will retry/resume", batch_id)
        raise task.retry(exc=exc, countdown=30)
    finally:
        session.close()


@celery_app.task(name="leadpilot.leads.source", bind=True, max_retries=3)
def source_leads(self, batch_id: str):
    return _run_stage(source_leads_impl, batch_id, self)


@celery_app.task(name="leadpilot.leads.enrich", bind=True, max_retries=3)
def enrich_leads(self, _prev=None, *, batch_id: str):
    return _run_stage(enrich_leads_impl, batch_id, self)


@celery_app.task(name="leadpilot.leads.find_emails", bind=True, max_retries=3)
def find_missing_emails(self, _prev=None, *, batch_id: str):
    return _run_stage(find_missing_emails_impl, batch_id, self)


@celery_app.task(name="leadpilot.leads.verify", bind=True, max_retries=3)
def verify_emails(self, _prev=None, *, batch_id: str):
    return _run_stage(verify_emails_impl, batch_id, self)


@celery_app.task(name="leadpilot.leads.finalize", bind=True, max_retries=3)
def finalize_lead_batch(self, _prev=None, *, batch_id: str):
    return _run_stage(finalize_lead_batch_impl, batch_id, self)


def start_lead_chain(batch_id: str):
    """Enqueue the full sourcing chain for a batch."""
    return chain(
        source_leads.s(batch_id),
        enrich_leads.s(batch_id=batch_id),
        find_missing_emails.s(batch_id=batch_id),
        verify_emails.s(batch_id=batch_id),
        finalize_lead_batch.s(batch_id=batch_id),
    ).apply_async()
