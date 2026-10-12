"""Lead endpoints - sourcing kickoff, listing, detail, GDPR delete, and
Feature 4's competitor displacement alerts."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.metering import metered
from app.core.rate_limiting import enforce_rate_limit
from app.api.schemas import (
    LeadBatchOut,
    LeadDetailOut,
    LeadListOut,
    LeadOut,
    SourceLeadsRequest,
)
from app.config import settings
from app.core.plans import PlanLimitExceeded, check_plan_quantity, plan_limit_response
from app.db.base import get_db
from app.db.models import (
    DisplacementAlert, Lead, LeadBatch, LeadStatus, Product, Strategy,
    StrategyStatus, SuppressionEntry, User,
)
from app.services import fpta_scoring
from app.services import local_business
from app.services.icp_extraction import ensure_pattern_key, extract_icp_criteria
from app.workers import lead_tasks

router = APIRouter(tags=["leads"])


def _owned_strategy(db: Session, strategy_id: uuid.UUID, current_user: User) -> Strategy:
    """Fetch a strategy and verify it belongs to current_user, else 404.

    Shared by every endpoint below so a strategy id from another account
    can never be probed, sourced, listed, or read - 404 either way (not
    403), so existence can't be inferred either.
    """
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    product = db.get(Product, strategy.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy


def _owned_lead(db: Session, lead_id: uuid.UUID, current_user: User) -> Lead:
    """Fetch a lead and verify it belongs (via its strategy's product) to
    current_user, else 404."""
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    strategy = db.get(Strategy, lead.strategy_id)
    product = db.get(Product, strategy.product_id) if strategy else None
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


# Rate limited: each call spends paid Apollo/Hunter credits.
@router.post("/strategies/{strategy_id}/leads/source", response_model=LeadBatchOut,
             status_code=202)
def source_leads_for_strategy(
    strategy_id: uuid.UUID,
    body: SourceLeadsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeadBatch:
    """Kick off the sourcing chain for a VERIFIED strategy.

    Hard gate: a strategy that has not passed all 10 verification passes
    cannot source a single lead (409)."""
    # Rate limit AFTER validation — see the note in strategies.py::create_strategy
    # and app/core/rate_limiting.py::enforce_rate_limit.
    enforce_rate_limit(str(current_user.id), "leads_source", "RATE_LIMIT_LEADS_SOURCE")

    strategy = _owned_strategy(db, strategy_id, current_user)
    if strategy.status is not StrategyStatus.VERIFIED:
        raise HTTPException(
            status_code=409,
            detail=(
                f"strategy status is '{strategy.status.value}' - leads can only "
                "be sourced for a strategy that passed all 10 verification passes"
            ),
        )

    # Plan limit (max_leads_per_strategy): refuse when the strategy is full,
    # otherwise ask for no more than the room left. The worker re-checks per
    # lead (app/workers/lead_tasks.py::source_leads_impl).
    room = lead_tasks.strategy_lead_room(db, strategy.id)
    if room is not None and room <= 0:
        try:
            check_plan_quantity(
                current_user, "max_leads_per_strategy",
                lead_tasks.strategy_lead_count(db, strategy.id) + 1,
                "This strategy already has that many leads.")
        except PlanLimitExceeded as exc:
            raise HTTPException(status_code=402, detail=plan_limit_response(exc))

    # P0-5b: both extractions are model calls on the account's daily limit.
    with metered(db, current_user, "icp"):
        if body.icp_criteria:
            # Local business mode: explicit criteria keep their own locations;
            # an empty list is filled from the service area (no model call).
            criteria = local_business.apply_to_criteria(db, strategy, body.icp_criteria,
                                                        explicit=True)
        else:
            criteria = extract_icp_criteria(db, strategy)

        # Bind this strategy to its playbook bucket. Sourcing is the first moment
        # the ICP is concrete, and every learning-loop query filters on
        # pattern_key -- see icp_extraction.ensure_pattern_key.
        ensure_pattern_key(db, strategy, criteria)

    requested = min(body.max_leads or settings.leads_max_per_run,
                    settings.leads_max_per_run,
                    room if room is not None else settings.leads_max_per_run)
    # F07: forecast the enrichment run; refused (429) before the batch exists.
    from app.api import spend_guard as spend_guard_api  # noqa: PLC0415

    forecast = spend_guard_api.guard_enrichment_run(db, current_user, strategy, requested)
    batch = LeadBatch(
        strategy_id=strategy.id,
        requested_leads=requested,
        icp_criteria_json=criteria,
        source_provider=settings.lead_source_provider,
        verifier_provider=settings.email_verifier_provider,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    spend_guard_api.link(db, forecast, batch_id=batch.id)  # F07

    lead_tasks.start_lead_chain(str(batch.id))
    return batch


@router.get("/strategies/{strategy_id}/leads", response_model=LeadListOut)
def list_leads(
    strategy_id: uuid.UUID,
    status: LeadStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="score", pattern="^(score|created|fpta)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LeadListOut:
    _owned_strategy(db, strategy_id, current_user)

    where = [Lead.strategy_id == strategy_id]
    if status is not None:
        where.append(Lead.status == status)

    total = db.execute(select(func.count(Lead.id)).where(*where)).scalar_one()
    # Feature Group 1: highest ai_booking_likelihood first by default.
    # Unscored leads (NULL) sort LAST, not as zero, and fall back to the old
    # creation order among themselves -- so a strategy with no scores yet
    # lists exactly as it always did.
    # Part 1 Feature 2 adds sort=fpta. Unscored leads sort LAST under both
    # score orders -- NULL is "never scored", not zero.
    if sort == "score":
        order = [Lead.ai_booking_likelihood.desc().nulls_last(), Lead.created_at]
    elif sort == "fpta":
        order = [Lead.fpta_overall.desc().nulls_last(), Lead.created_at]
    else:
        order = [Lead.created_at]
    items = db.execute(
        select(Lead).where(*where).order_by(*order).limit(limit).offset(offset)
    ).scalars().all()
    return LeadListOut(
        total=total, limit=limit, offset=offset,
        items=[LeadOut.model_validate(lead) for lead in items],
    )


@router.get("/leads/{lead_id}", response_model=LeadDetailOut)
def get_lead(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Lead:
    return _owned_lead(db, lead_id, current_user)


@router.get("/strategies/{strategy_id}/leads/{lead_id}", response_model=LeadDetailOut)
def get_strategy_lead(
    strategy_id: uuid.UUID,
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Lead:
    """Same payload as GET /leads/{lead_id}, scoped to one strategy.

    The published SDK's `ch.leads.get(strategy_id, lead_id)` calls this path
    (sdk/src/clienthunter/client.py::_LeadsResource.get); the route did not
    exist, so that method always raised NotFoundError. Ownership is checked
    on BOTH ids - the strategy first, so a lead id can't be probed through a
    strategy the caller doesn't own - and a lead that belongs to a different
    strategy of the same owner is still 404, because the path asserts the
    lead is in THIS strategy.
    """
    _owned_strategy(db, strategy_id, current_user)
    lead = _owned_lead(db, lead_id, current_user)
    if lead.strategy_id != strategy_id:
        raise HTTPException(status_code=404, detail="lead not found")
    return lead


@router.get("/leads/{lead_id}/provenance")
def get_lead_provenance(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Part 1 Feature 10: where every enriched field came from.

    Weakest source first, because the list exists to answer "what here should
    I not rely on?". `tracked: false` means no provenance was ever recorded
    for this prospect -- which is NOT the same as "unknown source", and the UI
    says which."""
    from app.services import provenance  # noqa: PLC0415

    lead = _owned_lead(db, lead_id, current_user)
    return provenance.for_lead(lead)


@router.get("/leads/{lead_id}/fpta")
def get_lead_fpta(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Part 1 Feature 2: the four sub-scores, each with its reason, the
    evidence behind it and the weight it carries in the overall.

    Returns `band: "unscored"` and null scores for a prospect that has never
    been scored -- honest, and different from a score of zero."""
    lead = _owned_lead(db, lead_id, current_user)
    return {"lead_id": str(lead.id), **fpta_scoring.detail(lead),
            "engagement": fpta_scoring.engagement_note(db, lead)}


@router.post("/leads/{lead_id}/fpta/rescore")
def rescore_lead_fpta(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Re-run F-P-T-A for one prospect.

    Costs a model call, so it is rate limited with the other lead writes. A
    model failure is not an error here: the deterministic baselines are
    written and `method` says `heuristic`, which is a usable score."""
    enforce_rate_limit(str(current_user.id), "fpta_rescore", "RATE_LIMIT_AI_ACTION")
    lead = _owned_lead(db, lead_id, current_user)
    local_business.refuse_if_customer(lead, "F-P-T-A scoring")
    with metered(db, current_user, "lead_scoring", refuse_after=False):
        fpta_scoring.score_lead(db, lead)
        return {"lead_id": str(lead.id), **fpta_scoring.detail(lead),
                "engagement": fpta_scoring.engagement_note(db, lead)}


@router.post("/strategies/{strategy_id}/leads/fpta/rescore")
def rescore_strategy_fpta(
    strategy_id: uuid.UUID,
    only_unscored: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Backfill F-P-T-A across a strategy's prospects.

    `only_unscored=true` (the default) is the safe one: it never overwrites a
    score someone has already read and acted on."""
    enforce_rate_limit(str(current_user.id), "fpta_rescore", "RATE_LIMIT_AI_ACTION")
    strategy = _owned_strategy(db, strategy_id, current_user)
    where = [Lead.strategy_id == strategy_id, Lead.status.in_(fpta_scoring.SCORABLE),
             # Imported customers are consumers: never scored (local business).
             Lead.source != local_business.CUSTOMER_SOURCE]
    if only_unscored:
        where.append(Lead.fpta_scored_at.is_(None))
    leads = db.execute(select(Lead).where(*where).limit(limit)).scalars().all()
    with metered(db, current_user, "lead_scoring", refuse_after=False):
        scored = fpta_scoring.score_leads(db, strategy, list(leads))
        return {"strategy_id": str(strategy_id), "scored": scored,
                "only_unscored": only_unscored}


@router.delete("/leads/{lead_id}", status_code=204)
def gdpr_delete_lead(
    lead_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """GDPR delete: erase the lead's personal data and write tombstones.

    - email/phone go onto the suppression list (reason: gdpr_delete), so
      the person is never contacted OR re-sourced by ANY strategy - the
      sourcing stage checks suppression first, always.
    - the lead row keeps only its id + provider external_id as a
      non-personal tombstone; the (strategy, source, external_id) unique
      key then blocks re-insertion within this strategy too.
    - the correspondence goes too: reply sender/subject/body/AI draft and the
      subject/body of every message to the person (counts' metadata kept;
      anything still scheduled is cancelled); provenance loses its values.
    - the lead is DROPPED and every live enrollment is stopped (reason
      lead_removed) in the same commit, through sequence_engine.stop_for_status.
    - F10: the SAME PERSON's other lead rows that this account's Champion
      Tracker linked by a job change (the old lead <-> the re-engagement lead
      at the new company, transitively) are erased the same way. The erasure
      request is about the person, not about one row.
    """
    lead = _owned_lead(db, lead_id, current_user)
    from app.services import champion_tracker  # noqa: PLC0415

    # Collected BEFORE erasing: the links are lead ids, which erasure keeps.
    linked = champion_tracker.linked_lead_ids(db, current_user.id, lead.id)
    _gdpr_erase_lead(db, lead, current_user)
    for other_id in sorted(linked, key=str):
        other = db.get(Lead, other_id)
        if other is None or champion_tracker.is_erased(other):
            continue
        # Same account only: _owned_lead raises 404 for anything else.
        _gdpr_erase_lead(db, _owned_lead(db, other.id, current_user), current_user)


def _gdpr_erase_lead(db: Session, lead: Lead, current_user: User) -> None:
    """Erase ONE lead row (the body of the GDPR delete)."""

    def _suppress(email: str | None, phone: str | None) -> None:
        if email:
            exists = db.execute(
                select(SuppressionEntry.id).where(SuppressionEntry.email == email.lower().strip())
            ).scalar_one_or_none()
            if not exists:
                db.add(SuppressionEntry(email=email.lower().strip(), reason="gdpr_delete"))
        if phone and phone.strip():
            # NEW-04: compared normalised and written canonical, so the same
            # number in another format is neither missed nor duplicated.
            if not lead_tasks.is_suppressed(db, phone=phone):
                db.add(SuppressionEntry(phone=lead_tasks.suppression_phone(phone),
                                        reason="gdpr_delete"))

    # Part 1 Feature 9: the erasure event is written BEFORE the data goes,
    # with the identifier and owner denormalized onto the row, so the proof
    # that the request was honoured survives the deletion it is proof of.
    from app.services import consent  # noqa: PLC0415

    consent.record_erasure(db, lead, actor=current_user)

    # Email network: the same person's contact row in THIS account's network
    # (and any saved first email to them) goes too, in the same commit.
    from app.services import email_network  # noqa: PLC0415

    email_network.erase_person(db, current_user.id, email=lead.email, lead_id=lead.id)
    _suppress(lead.email, lead.phone)
    # Feature Group 5: the LinkedIn profile is personal data AND a contact
    # route -- suppress it like the email and phone, then erase it.
    if lead.linkedin_url:
        from app.db.models import LinkedInSuppression  # noqa: PLC0415
        from app.services.linkedin_outreach import normalize_profile  # noqa: PLC0415
        from app.workers.lead_tasks import is_suppressed  # noqa: PLC0415

        profile = normalize_profile(lead.linkedin_url)
        if profile and not is_suppressed(db, linkedin=lead.linkedin_url):
            db.add(LinkedInSuppression(profile=profile, reason="gdpr_delete"))

    # Erase personal data; keep the non-personal tombstone.
    lead.full_name = None
    lead.title = None
    lead.email = None
    lead.phone = None
    lead.company = None
    lead.enrichment_json = {"gdpr_deleted": True}
    # Feature Groups 1/2/5: everything else that describes the person.
    lead.linkedin_url = None
    lead.linkedin_provider_id = None
    lead.linkedin_posts_json = None
    lead.company_news_json = None
    lead.loom_video_json = None
    lead.ai_score_reason = None
    lead.ai_score_factors = None
    # Product defect #11: scores and their reasons are derived from the
    # person's data, so they go too.
    lead.ai_booking_likelihood = None
    lead.conversion_factors_json = None
    lead.fpta_fit = lead.fpta_problem = lead.fpta_timing = None
    lead.fpta_access = lead.fpta_overall = None
    lead.fpta_reasons_json = None
    lead.fpta_method = None
    lead.fpta_scored_at = None
    lead.status = LeadStatus.DROPPED
    # F02 Signal Radar: signals hold post excerpts and headlines derived from
    # the fields erased above. The lead row is a tombstone, not a delete, so
    # the FK cascade never fires -- they are deleted here, in the same commit.
    from app.services import signal_radar  # noqa: PLC0415

    signal_radar.erase_for_lead(db, lead.id)
    # F06: a Quickstart draft quotes the person's name and company. The lead
    # row is tombstoned, not deleted, so its FK cascade never fires -- erase
    # the drafts explicitly, in the same transaction.
    from app.services import quickstart  # noqa: PLC0415

    quickstart.erase_lead_drafts(db, lead.id)
    # F04: a Reply Copilot draft quotes the person and answers their reply.
    # Same reason as above: erased explicitly, in the same transaction.
    from app.services import reply_copilot  # noqa: PLC0415

    reply_copilot.erase_for_lead(db, lead.id)
    # F10: a recorded job change names the person's employers and holds a hash
    # of the old address -- scrub it (the row stays as a non-personal
    # tombstone so the counts survive), in the same commit.
    from app.services import champion_tracker  # noqa: PLC0415

    champion_tracker.erase_for_lead(db, lead.id)
    # GDPR gap B (docs/features/gdpr-erasure.md): the correspondence itself --
    # the replies the person sent (address, subject, body, the AI draft answer)
    # and the subject/body of every message written to them. The non-personal
    # metadata the reply-rate and send counts read is kept. A message that
    # could still go out is cancelled first. And provenance keeps WHERE each
    # field came from but no longer WHAT it was.
    from app.services import account_erasure  # noqa: PLC0415

    account_erasure.erase_lead_correspondence(db, lead.id)
    lead.provenance_json = account_erasure.scrub_provenance(lead.provenance_json)
    # The lead is now DROPPED: end its sequences through the shared rule every
    # status writer uses (sequence_engine.stop_for_status, reason
    # lead_removed), in the same transaction. Before, the enrollments stayed
    # ACTIVE and only the send-time gates (dropped lead, suppression) kept
    # the erased person from being contacted (gaps-sweep-2 review L5).
    from app.services import sequence_engine  # noqa: PLC0415

    sequence_engine.stop_for_status(db, lead, commit=False)
    db.commit()
    # Feature Group 4: forget which CRM record this person was synced to.
    # (What the CRM itself holds is the CRM owner's to erase.)
    from app.services import crm_sync  # noqa: PLC0415

    crm_sync.forget_local(db, "lead", lead.id)


# ---------------------------------------------------------------------------
# Feature 4 — competitor displacement alerts
# ---------------------------------------------------------------------------
#
# Alerts are WRITTEN by the twelve-hourly sweep
# (app/workers/displacement_tasks.py). These two routes are the only place a
# human touches them: read the list, mark one acted or dismissed. Neither
# sends anything -- `suggested_dm` is a draft the founder copies, edits and
# sends themselves.


class DisplacementAlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None
    company: str | None
    matched_keywords: list
    post_excerpt: str
    post_url: str | None
    suggested_dm: str | None
    # The status to DISPLAY: "expired" for a pending alert past expires_at,
    # otherwise the stored value. See displacement_monitor.effective_status
    # for why expiry is derived rather than swept.
    status: str
    acted_at: datetime | None
    expires_at: datetime
    created_at: datetime


class DisplacementPatchIn(BaseModel):
    status: Literal["acted", "dismissed"]


def _alert_out(alert: DisplacementAlert, lead: Lead, now: datetime) -> DisplacementAlertOut:
    from app.services import displacement_monitor  # noqa: PLC0415

    return DisplacementAlertOut(
        id=alert.id,
        lead_id=alert.lead_id,
        lead_name=lead.full_name if lead else None,
        company=lead.company if lead else None,
        matched_keywords=alert.matched_keywords or [],
        post_excerpt=alert.post_excerpt,
        post_url=alert.post_url,
        suggested_dm=alert.suggested_dm,
        status=displacement_monitor.effective_status(alert, now),
        acted_at=alert.acted_at,
        expires_at=alert.expires_at,
        created_at=alert.created_at,
    )


@router.get("/strategies/{strategy_id}/displacement-alerts",
            response_model=list[DisplacementAlertOut])
def list_displacement_alerts(
    strategy_id: uuid.UUID,
    status: Literal["pending", "acted", "dismissed", "expired"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[DisplacementAlertOut]:
    """Leads in this campaign who publicly complained, newest first.

    `status=pending` deliberately EXCLUDES alerts past their expiry, and
    `status=expired` returns exactly those -- a two-week-old "saw your post"
    is worse than no message, so a stale alert must not sit in the queue of
    things to act on. Both are derived from expires_at rather than swept, so
    the list is correct whether or not any background job ran.
    """
    _owned_strategy(db, strategy_id, current_user)
    now = datetime.now(timezone.utc)

    where = [Lead.strategy_id == strategy_id]
    if status == "expired":
        where += [DisplacementAlert.alert_status == "pending",
                  DisplacementAlert.expires_at <= now]
    elif status == "pending":
        where += [DisplacementAlert.alert_status == "pending",
                  DisplacementAlert.expires_at > now]
    elif status is not None:
        where.append(DisplacementAlert.alert_status == status)

    rows = db.execute(
        select(DisplacementAlert, Lead)
        .join(Lead, Lead.id == DisplacementAlert.lead_id)
        .where(*where)
        .order_by(DisplacementAlert.created_at.desc())
        .limit(limit).offset(offset)
    ).all()
    return [_alert_out(alert, lead, now) for alert, lead in rows]


@router.patch("/alerts/{alert_id}/displacement", response_model=DisplacementAlertOut)
def patch_displacement_alert(
    alert_id: uuid.UUID,
    body: DisplacementPatchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DisplacementAlertOut:
    """Mark an alert acted on or dismissed.

    `acted` stamps acted_at; `dismissed` does not, because nothing was acted
    on and a timestamp saying otherwise would be a lie the analytics could
    read. An expired alert can still be marked -- the founder may act late,
    and refusing the write would leave it stuck in the list forever.
    """
    enforce_rate_limit(str(current_user.id), "crm_write", "RATE_LIMIT_CRM_WRITE")
    alert = db.get(DisplacementAlert, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert not found")
    # Ownership travels through the alert's lead, and answers 404 for someone
    # else's alert exactly as every other route here does.
    lead = _owned_lead(db, alert.lead_id, current_user)

    alert.alert_status = body.status
    alert.acted_at = datetime.now(timezone.utc) if body.status == "acted" else None
    db.commit()
    return _alert_out(alert, lead, datetime.now(timezone.utc))
