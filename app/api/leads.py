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
from app.core.rate_limiting import enforce_rate_limit
from app.api.schemas import (
    LeadBatchOut,
    LeadDetailOut,
    LeadListOut,
    LeadOut,
    SourceLeadsRequest,
)
from app.config import settings
from app.db.base import get_db
from app.db.models import (
    DisplacementAlert, Lead, LeadBatch, LeadStatus, Product, Strategy,
    StrategyStatus, SuppressionEntry, User,
)
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

    criteria = body.icp_criteria or extract_icp_criteria(db, strategy)

    # Bind this strategy to its playbook bucket. Sourcing is the first moment
    # the ICP is concrete, and every learning-loop query filters on
    # pattern_key -- see icp_extraction.ensure_pattern_key.
    ensure_pattern_key(db, strategy, criteria)

    batch = LeadBatch(
        strategy_id=strategy.id,
        requested_leads=min(body.max_leads or settings.leads_max_per_run,
                            settings.leads_max_per_run),
        icp_criteria_json=criteria,
        source_provider=settings.lead_source_provider,
        verifier_provider=settings.email_verifier_provider,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    lead_tasks.start_lead_chain(str(batch.id))
    return batch


@router.get("/strategies/{strategy_id}/leads", response_model=LeadListOut)
def list_leads(
    strategy_id: uuid.UUID,
    status: LeadStatus | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="score", pattern="^(score|created)$"),
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
    order = ([Lead.ai_booking_likelihood.desc().nulls_last(), Lead.created_at]
             if sort == "score" else [Lead.created_at])
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
    """
    lead = _owned_lead(db, lead_id, current_user)

    def _suppress(email: str | None, phone: str | None) -> None:
        if email:
            exists = db.execute(
                select(SuppressionEntry.id).where(SuppressionEntry.email == email.lower().strip())
            ).scalar_one_or_none()
            if not exists:
                db.add(SuppressionEntry(email=email.lower().strip(), reason="gdpr_delete"))
        if phone:
            exists = db.execute(
                select(SuppressionEntry.id).where(SuppressionEntry.phone == phone.strip())
            ).scalar_one_or_none()
            if not exists:
                db.add(SuppressionEntry(phone=phone.strip(), reason="gdpr_delete"))

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
    lead.status = LeadStatus.DROPPED
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
