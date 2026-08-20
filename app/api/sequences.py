"""Sequence endpoints — create, enroll, inspect (M3)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import (
    ChannelType,
    EnrollmentStatus,
    LeadStatus,
    Product,
    Sequence,
    SequenceEnrollment,
    SequenceStep,
    SequenceStatus,
    Strategy,
    StrategyStatus,
    User,
    WhatsAppStepKind,
    WhatsAppTemplate,
    WhatsAppTemplateStatus,
)
from app.services import sequence_engine as engine
from app.services.whatsapp_templates import _validate_variable_descriptions

router = APIRouter(tags=["sequences"])


def _owned_strategy(db: Session, strategy_id: uuid.UUID, current_user: User) -> Strategy:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    product = db.get(Product, strategy.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy


def _owned_sequence(db: Session, sequence_id: uuid.UUID, current_user: User) -> Sequence:
    sequence = db.get(Sequence, sequence_id)
    if sequence is None:
        raise HTTPException(status_code=404, detail="sequence not found")
    _owned_strategy(db, sequence.strategy_id, current_user)
    return sequence


class StepIn(BaseModel):
    step_no: int = Field(ge=1, le=20)
    template: str = Field(min_length=1, description="Messaging brief Claude personalizes per lead")
    variant: str = Field(default="A", max_length=20)
    delay_days: int = Field(default=3, ge=0, le=60, description="Wait after the previous step")
    # --- M4 Chunk 3: multi-channel steps ---------------------------------
    channel: ChannelType | None = Field(
        default=None, description="Overrides the sequence channel for this "
        "step (e.g. a WhatsApp follow-up inside an email sequence)")
    whatsapp_kind: WhatsAppStepKind | None = Field(
        default=None, description="WhatsApp steps only: 'template' (cold-"
        "capable) or 'text' (reply-handling, only sends inside an open 24h "
        "customer-service window)")
    whatsapp_template_id: uuid.UUID | None = None
    variable_mapping: dict[str, str] | None = Field(
        default=None, description="Per-variable fill sources: 'lead.<field>' "
        "or a free-text brief Claude fills from enrichment + messaging")


class SequenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    channel: ChannelType = ChannelType.EMAIL
    booking_url: str | None = Field(default=None, max_length=500)
    steps: list[StepIn] = Field(min_length=1, max_length=20)


class StepOut(StepIn):
    model_config = ConfigDict(from_attributes=True)


class SequenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    name: str
    channel: ChannelType
    status: SequenceStatus
    booking_url: str | None
    steps: list[StepOut]


class EnrollRequest(BaseModel):
    lead_statuses: list[LeadStatus] = Field(
        default=[LeadStatus.VERIFIED],
        description="Which leads to enroll; defaults to verified-only",
    )


@router.post("/strategies/{strategy_id}/sequences", response_model=SequenceOut, status_code=201)
def create_sequence(
    strategy_id: uuid.UUID,
    body: SequenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Sequence:
    strategy = _owned_strategy(db, strategy_id, current_user)
    if body.channel is ChannelType.LINKEDIN or any(
        s.channel is ChannelType.LINKEDIN for s in body.steps
    ):
        raise HTTPException(status_code=422,
                            detail="the linkedin channel is not available yet")
    step_nos = [s.step_no for s in body.steps]
    if sorted(step_nos) != list(range(1, len(step_nos) + 1)):
        raise HTTPException(status_code=422,
                            detail="steps must be numbered 1..n with no gaps")

    # M4 Chunk 3: validate every WhatsApp step at creation time.
    for s in body.steps:
        effective = s.channel or body.channel
        if effective is not ChannelType.WHATSAPP:
            if s.whatsapp_kind or s.whatsapp_template_id or s.variable_mapping:
                raise HTTPException(
                    status_code=422,
                    detail=f"step {s.step_no}: whatsapp_* fields are only "
                           "valid on WhatsApp steps")
            continue
        kind = s.whatsapp_kind or WhatsAppStepKind.TEMPLATE
        s.whatsapp_kind = kind
        if kind is WhatsAppStepKind.TEXT:
            if s.step_no == 1:
                raise HTTPException(
                    status_code=422,
                    detail=f"step {s.step_no}: a free-form WhatsApp step "
                           "cannot open a sequence — free-form only sends "
                           "inside a 24h customer-service window the LEAD "
                           "opens by messaging first. Use an approved "
                           "template for the first WhatsApp touch.")
            continue
        # kind == TEMPLATE: must reference a known, non-rejected template
        # with a complete variable mapping. Approval is re-verified at
        # send time (and by the adapter guard) — a template still under
        # review may be referenced, it just won't send until approved.
        if s.whatsapp_template_id is None:
            raise HTTPException(
                status_code=422,
                detail=f"step {s.step_no}: cold WhatsApp steps must "
                       "reference a whatsapp_template_id")
        tmpl = db.get(WhatsAppTemplate, s.whatsapp_template_id)
        if tmpl is None:
            raise HTTPException(status_code=422,
                                detail=f"step {s.step_no}: template not found")
        if tmpl.status is WhatsAppTemplateStatus.REJECTED:
            reason = tmpl.rejection_reason or "no reason given"
            raise HTTPException(
                status_code=422,
                detail=f"step {s.step_no}: template '{tmpl.name}' was "
                       f"REJECTED by Meta ({reason}) — edit and resubmit "
                       "it first")
        expected = tmpl.variable_descriptions_json or {}
        try:
            slots = {int(n): "" for n in expected}
            _validate_variable_descriptions(slots, s.variable_mapping or expected)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"step {s.step_no}: variable_mapping must cover "
                       f"exactly the template's variables "
                       f"{sorted(expected)} — {exc}")

    sequence = Sequence(strategy_id=strategy.id, name=body.name,
                        channel=body.channel, booking_url=body.booking_url,
                        status=SequenceStatus.DRAFT)
    db.add(sequence)
    db.flush()
    for s in body.steps:
        db.add(SequenceStep(sequence_id=sequence.id, step_no=s.step_no,
                            template=s.template, variant=s.variant,
                            delay_days=s.delay_days,
                            channel=s.channel,
                            whatsapp_kind=s.whatsapp_kind,
                            whatsapp_template_id=s.whatsapp_template_id,
                            variable_mapping_json=s.variable_mapping))
    db.commit()
    db.refresh(sequence)
    return sequence


@router.post("/sequences/{sequence_id}/enroll", status_code=202)
def enroll(
    sequence_id: uuid.UUID,
    body: EnrollRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Enroll matching leads and schedule their first message. Requires a
    VERIFIED strategy with an active campaign — same gate as sourcing."""
    sequence = _owned_sequence(db, sequence_id, current_user)
    strategy = db.get(Strategy, sequence.strategy_id)
    if strategy.status is not StrategyStatus.VERIFIED:
        raise HTTPException(status_code=409,
                            detail="strategy has not passed all 10 verification passes")
    if strategy.campaign_state != engine.CAMPAIGN_ACTIVE:
        raise HTTPException(status_code=409,
                            detail=f"campaign is {strategy.campaign_state}: "
                                   f"{strategy.campaign_pause_reason}")

    enrolled = engine.enroll_leads(db, sequence, lead_statuses=body.lead_statuses)
    if enrolled and sequence.status is SequenceStatus.DRAFT:
        sequence.status = SequenceStatus.ACTIVE
        db.commit()
    return {"enrolled": enrolled}


@router.get("/sequences/{sequence_id}", response_model=None)
def get_sequence(
    sequence_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    sequence = _owned_sequence(db, sequence_id, current_user)
    counts = dict(db.execute(
        select(SequenceEnrollment.status, func.count(SequenceEnrollment.id))
        .where(SequenceEnrollment.sequence_id == sequence_id)
        .group_by(SequenceEnrollment.status)
    ).all())
    return {
        "sequence": SequenceOut.model_validate(sequence).model_dump(),
        "enrollments": {status.value: counts.get(status, 0) for status in EnrollmentStatus},
    }