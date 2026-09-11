"""Deals — revenue linked back to a lead and a campaign.

Written three ways: POST /deals by hand, "Log Meeting Outcome = closed won"
(app/services/meeting_followup.py), and the HubSpot/Salesforce deal-stage
webhooks. Read by the revenue dashboard (app/api/revenue.py).

"CAMPAIGN" IS A STRATEGY. One strategy owns one outreach campaign in this
schema (Strategy.campaign_state), so `strategy_id` is the campaign link. When
only a lead is given it is derived from the lead, so a deal logged from the
lead page is attributed without the user having to know that.

Money crosses the API as a decimal `value` and is stored as integer cents --
see the Deal model's docstring for why.
"""

# NOTE: deliberately NO `from __future__ import annotations` (FastAPI).

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.leads import _owned_lead, _owned_strategy
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import CrmActivityKind, Deal, DealStage, User

router = APIRouter(prefix="/deals", tags=["deals"])

_WRITE_LIMIT = "RATE_LIMIT_CRM_WRITE"


def _cents(value: float) -> int:
    return max(0, int(round(float(value) * 100)))


class DealIn(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    value: float = Field(ge=0, le=1e12)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    stage: DealStage = DealStage.WON
    close_date: date | None = None
    lead_id: uuid.UUID | None = None
    strategy_id: uuid.UUID | None = None
    notes: str | None = Field(default=None, max_length=10_000)

    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        if not value.isalpha():
            raise ValueError("currency must be a 3-letter ISO code")
        return value.upper()


class DealPatch(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    value: float | None = Field(default=None, ge=0, le=1e12)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    stage: DealStage | None = None
    close_date: date | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class DealOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    value_cents: int
    currency: str
    stage: DealStage
    close_date: date | None
    lead_id: uuid.UUID | None
    strategy_id: uuid.UUID | None
    source: str
    external_ref: str | None
    notes: str | None
    created_at: datetime

    @computed_field
    @property
    def value(self) -> float:
        return self.value_cents / 100


class DealListOut(BaseModel):
    total: int
    items: list[DealOut]


def _crm_push(db: Session, user: User, deal: Deal) -> None:
    """Feature Group 4: mirror the deal to the connected CRM right away."""
    from app.services import crm_sync  # noqa: PLC0415
    from app.workers import crm_tasks  # noqa: PLC0415

    if crm_sync.has_connection(db, user.id):
        crm_tasks.enqueue_push("deal", user.id, deal.id)


def _owned_deal(db: Session, deal_id: uuid.UUID, user: User) -> Deal:
    deal = db.get(Deal, deal_id)
    if deal is None or deal.user_id != user.id:
        raise HTTPException(status_code=404, detail="deal not found")
    return deal


@router.post("", response_model=DealOut, status_code=201)
def create_deal(body: DealIn, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> Deal:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)
    lead = _owned_lead(db, body.lead_id, current_user) if body.lead_id else None
    strategy_id = body.strategy_id
    if strategy_id is not None:
        _owned_strategy(db, strategy_id, current_user)
        if lead is not None and lead.strategy_id != strategy_id:
            raise HTTPException(status_code=422,
                                detail="lead_id belongs to a different campaign")
    elif lead is not None:
        strategy_id = lead.strategy_id

    close_date = body.close_date
    if close_date is None and body.stage is DealStage.WON:
        close_date = date.today()
    deal = Deal(
        user_id=current_user.id, lead_id=lead.id if lead else None,
        strategy_id=strategy_id,
        name=(body.name or (lead.company or lead.full_name if lead else None)
              or "Deal")[:200],
        value_cents=_cents(body.value), currency=body.currency, stage=body.stage,
        close_date=close_date, source="manual", notes=body.notes,
    )
    db.add(deal)
    db.flush()
    if lead is not None:
        from app.services import crm_events  # noqa: PLC0415

        crm_events.record_activity(
            db, lead.id, CrmActivityKind.DEAL_CREATED, actor_user_id=current_user.id,
            to_value=f"{deal.value_cents / 100:.2f} {deal.currency}",
            meta={"deal_id": str(deal.id), "source": "manual"},
        )
    db.commit()
    db.refresh(deal)
    _crm_push(db, current_user, deal)
    return deal


@router.get("", response_model=DealListOut)
def list_deals(strategy_id: uuid.UUID | None = None, stage: DealStage | None = None,
               lead_id: uuid.UUID | None = None,
               limit: int = Query(default=50, ge=1, le=200),
               offset: int = Query(default=0, ge=0),
               db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> DealListOut:
    where = [Deal.user_id == current_user.id]
    if strategy_id is not None:
        where.append(Deal.strategy_id == strategy_id)
    if stage is not None:
        where.append(Deal.stage == stage)
    if lead_id is not None:
        where.append(Deal.lead_id == lead_id)
    total = db.execute(select(func.count(Deal.id)).where(*where)).scalar_one()
    items = db.execute(
        select(Deal).where(*where)
        .order_by(Deal.close_date.desc().nulls_last(), Deal.created_at.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    return DealListOut(total=total, items=[DealOut.model_validate(d) for d in items])


@router.get("/{deal_id}", response_model=DealOut)
def get_deal(deal_id: uuid.UUID, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)) -> Deal:
    return _owned_deal(db, deal_id, current_user)


@router.patch("/{deal_id}", response_model=DealOut)
def update_deal(deal_id: uuid.UUID, body: DealPatch, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> Deal:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)
    deal = _owned_deal(db, deal_id, current_user)
    changes = body.model_dump(exclude_unset=True)
    if "value" in changes and changes["value"] is not None:
        deal.value_cents = _cents(changes.pop("value"))
    changes.pop("value", None)
    if changes.get("currency"):
        changes["currency"] = changes["currency"].upper()
    for key, value in changes.items():
        if value is not None or key in ("close_date", "notes"):
            setattr(deal, key, value)
    if deal.stage is DealStage.WON and deal.close_date is None:
        deal.close_date = date.today()
    db.commit()
    db.refresh(deal)
    _crm_push(db, current_user, deal)
    return deal


@router.delete("/{deal_id}", status_code=204)
def delete_deal(deal_id: uuid.UUID, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> None:
    enforce_rate_limit(str(current_user.id), "crm_write", _WRITE_LIMIT)
    db.delete(_owned_deal(db, deal_id, current_user))
    db.commit()
