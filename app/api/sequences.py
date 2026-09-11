"""Sequence endpoints — create, enroll, inspect (M3)."""

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
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
    # --- Engagement Hub, Feature 1 ---------------------------------------
    # NOT the same timer as delay_days. delay_days waits after this step
    # SENDS before the next one is scheduled; these two govern what happens
    # when the lead never replies to this step at all. See migration 0020.
    followup_enabled: bool = Field(
        default=True, description="Automatically follow up when this step "
        "gets no reply")
    followup_delay_hours: int = Field(
        default=72, ge=1, le=2160, description="Hours of silence after this "
        "step before the automatic follow-up fires (max 90 days)")
    # --- Feature Group 5 --------------------------------------------------
    linkedin_action: Literal["auto", "connect", "message", "inmail"] | None = Field(
        default=None, description="LinkedIn steps only: 'auto' (default) = "
        "message if connected, InMail for a Premium lead, else a connection "
        "request")


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
    # Feature Group 5: LinkedIn steps are available. linkedin_action belongs
    # on LinkedIn steps only, and defaults to `auto` there.
    for s in body.steps:
        if (s.channel or body.channel) is ChannelType.LINKEDIN:
            s.linkedin_action = s.linkedin_action or "auto"
        elif s.linkedin_action is not None:
            raise HTTPException(
                status_code=422,
                detail=f"step {s.step_no}: linkedin_action is only valid on "
                       "LinkedIn steps")
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
                            variable_mapping_json=s.variable_mapping,
                            followup_enabled=s.followup_enabled,
                            followup_delay_hours=s.followup_delay_hours,
                            linkedin_action=s.linkedin_action))
    db.commit()
    db.refresh(sequence)
    return sequence


def _launch_checks(db: Session, sequence: Sequence) -> None:
    strategy = db.get(Strategy, sequence.strategy_id)
    if strategy.status is not StrategyStatus.VERIFIED:
        raise HTTPException(status_code=409,
                            detail="strategy has not passed all 10 verification passes")
    if strategy.campaign_state != engine.CAMPAIGN_ACTIVE:
        raise HTTPException(status_code=409,
                            detail=f"campaign is {strategy.campaign_state}: "
                                   f"{strategy.campaign_pause_reason}")


def _launch(db: Session, sequence: Sequence, lead_statuses) -> int:
    enrolled = engine.enroll_leads(db, sequence, lead_statuses=lead_statuses)
    if enrolled and sequence.status in (SequenceStatus.DRAFT, SequenceStatus.PENDING_APPROVAL):
        sequence.status = SequenceStatus.ACTIVE
        db.commit()
    return enrolled


@router.post("/sequences/{sequence_id}/enroll", status_code=202)
def enroll(
    sequence_id: uuid.UUID,
    body: EnrollRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Enroll matching leads and schedule their first message. Requires a
    VERIFIED strategy with an active campaign — same gate as sourcing.

    Feature Group 8: an SDR's first launch of a sequence, in a workspace that
    requires approval, is held as `pending_approval` instead -- nothing is
    enrolled or scheduled until a manager approves it."""
    sequence = _owned_sequence(db, sequence_id, current_user)
    _launch_checks(db, sequence)
    if _needs_approval(db, request, sequence):
        return _request_approval(db, request, sequence, body)
    result = {"enrolled": _launch(db, sequence, body.lead_statuses)}
    # Feature Group 9: launching into a sick sending domain is allowed, but
    # never silently.
    from app.services import deliverability  # noqa: PLC0415

    warning = deliverability.launch_warning(db, current_user.id)
    if warning:
        result["warning"] = warning
    return result


# --------------------------------------------------------------------------
# Feature Group 8: manager approval
# --------------------------------------------------------------------------


def _role(request: Request) -> str:
    return getattr(request.state, "workspace_role", "owner")


def _actor(request: Request, fallback: User) -> User:
    return getattr(request.state, "actor", None) or fallback


def _needs_approval(db: Session, request: Request, sequence: Sequence) -> bool:
    from app.db.models import Workspace  # noqa: PLC0415

    if _role(request) != "sdr" or sequence.approved_at is not None:
        return False
    ws_id = getattr(request.state, "workspace_id", None)
    ws = db.get(Workspace, ws_id) if ws_id else None
    return ws is None or bool(ws.approval_required)


def _request_approval(db: Session, request: Request, sequence: Sequence,
                      body: EnrollRequest) -> dict:
    from app.db.models import Workspace  # noqa: PLC0415
    from app.services import workspaces  # noqa: PLC0415
    from app.workers import notification_tasks  # noqa: PLC0415

    actor = _actor(request, None)
    sequence.status = SequenceStatus.PENDING_APPROVAL
    sequence.approval_requested_by_user_id = actor.id if actor else None
    sequence.approval_requested_at = datetime.now(timezone.utc)
    sequence.approval_note = None
    sequence.approval_payload_json = {"lead_statuses": [s.value for s in body.lead_statuses]}
    db.commit()
    ws = db.get(Workspace, getattr(request.state, "workspace_id", None))
    for user_id in (workspaces.approvers(db, ws) if ws else []):
        if actor is None or user_id != actor.id:
            notification_tasks.enqueue_event(
                user_id, "approval_requested", title="Campaign awaiting approval",
                body=f"{actor.email if actor else 'An SDR'} wants to launch “{sequence.name}”.",
                deep_link=f"/campaigns?strategy={sequence.strategy_id}&tab=sequences",
                data={"sequenceId": str(sequence.id), "strategyId": str(sequence.strategy_id)},
            )
    return {"enrolled": 0, "status": SequenceStatus.PENDING_APPROVAL.value}


def _require_approver(request: Request) -> None:
    if _role(request) not in ("owner", "manager"):
        raise HTTPException(status_code=403, detail="Approving a launch needs a manager.")


def _notify_decision(sequence: Sequence, approved: bool, actor: User) -> None:
    from app.workers import notification_tasks  # noqa: PLC0415

    if sequence.approval_requested_by_user_id is None:
        return
    verdict = "approved" if approved else "declined"
    note = f" Note: {sequence.approval_note}" if sequence.approval_note else ""
    notification_tasks.enqueue_event(
        sequence.approval_requested_by_user_id, "approval_decided",
        title=f"Campaign {verdict}",
        body=f"{actor.email} {verdict} “{sequence.name}”.{note}",
        deep_link=f"/campaigns?strategy={sequence.strategy_id}&tab=sequences",
        data={"sequenceId": str(sequence.id), "approved": str(approved).lower()},
    )


@router.post("/sequences/{sequence_id}/approve")
def approve_sequence(
    sequence_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_approver(request)
    sequence = _owned_sequence(db, sequence_id, current_user)
    if sequence.status is not SequenceStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail="this sequence is not awaiting approval")
    _launch_checks(db, sequence)
    actor = _actor(request, current_user)
    payload = EnrollRequest(**(sequence.approval_payload_json or {}))
    sequence.approved_by_user_id = actor.id
    sequence.approved_at = datetime.now(timezone.utc)
    db.commit()
    enrolled = _launch(db, sequence, payload.lead_statuses)
    if sequence.status is SequenceStatus.PENDING_APPROVAL:
        # Approved, but no lead matched yet: it can be launched again later
        # without another approval.
        sequence.status = SequenceStatus.DRAFT
        db.commit()
    _notify_decision(sequence, True, actor)
    return {"status": sequence.status.value, "enrolled": enrolled}


class RejectRequest(BaseModel):
    note: str = Field(default="", max_length=1000)


@router.post("/sequences/{sequence_id}/reject")
def reject_sequence(
    sequence_id: uuid.UUID,
    body: RejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_approver(request)
    sequence = _owned_sequence(db, sequence_id, current_user)
    if sequence.status is not SequenceStatus.PENDING_APPROVAL:
        raise HTTPException(status_code=409, detail="this sequence is not awaiting approval")
    sequence.status = SequenceStatus.DRAFT
    sequence.approval_note = body.note.strip() or None
    db.commit()
    _notify_decision(sequence, False, _actor(request, current_user))
    return {"status": sequence.status.value}


@router.get("/approvals")
def list_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Launch requests in this workspace: pending ones, and declined ones
    (so the SDR can read the note)."""
    from app.db.models import Product  # noqa: PLC0415

    rows = db.execute(
        select(Sequence, Product.name)
        .join(Strategy, Strategy.id == Sequence.strategy_id)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == current_user.id,
               Sequence.approval_requested_at.isnot(None),
               Sequence.approved_at.is_(None))
        .order_by(Sequence.approval_requested_at.desc())
    ).all()
    emails = {u.id: u.email for u in db.execute(select(User).where(User.id.in_(
        [s.approval_requested_by_user_id for s, _ in rows
         if s.approval_requested_by_user_id]))).scalars()}
    return [{
        "sequence_id": str(s.id), "sequence_name": s.name, "strategy_id": str(s.strategy_id),
        "campaign": name, "status": s.status.value,
        "state": "pending" if s.status is SequenceStatus.PENDING_APPROVAL else "declined",
        "requested_by": emails.get(s.approval_requested_by_user_id),
        "requested_at": s.approval_requested_at.isoformat() if s.approval_requested_at else None,
        "note": s.approval_note,
        "lead_statuses": (s.approval_payload_json or {}).get("lead_statuses", []),
    } for s, name in rows]


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

# --------------------------------------------------------------------------
# Engagement Hub, Feature 1 — per-step follow-up settings
# --------------------------------------------------------------------------


class FollowupSettingsIn(BaseModel):
    """Both fields optional, so the toggle and the delay input are
    independent controls rather than one form that must send both."""

    enabled: bool | None = None
    delay_hours: int | None = Field(
        default=None, ge=1, le=2160,
        description="Hours of silence before the automatic follow-up fires. "
                    "Capped at 90 days: past that the sweep is holding an "
                    "enrollment open for a quarter, which is a state somebody "
                    "should be looking at rather than a setting.")


@router.post("/sequences/{sequence_id}/steps/{step_no}/followup-settings")
def update_followup_settings(
    sequence_id: uuid.UUID,
    step_no: int,
    body: FollowupSettingsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Turn the automatic follow-up on or off for one step, and set its delay.

    POST rather than PATCH because that is the path the brief specifies, and
    the operation is idempotent either way -- it writes exactly the fields it
    was sent.

    Changing the delay takes effect on the NEXT sweep, including for
    enrollments that are already waiting: the sweep compares `now - sent_at`
    against the CURRENT value every time it runs rather than storing a due
    date, so shortening the delay releases messages that were already overdue
    under the new setting instead of only applying to sends from here on.
    """
    _owned_sequence(db, sequence_id, current_user)
    step = db.execute(
        select(SequenceStep).where(SequenceStep.sequence_id == sequence_id,
                                   SequenceStep.step_no == step_no)
    ).scalars().first()
    if step is None:
        raise HTTPException(status_code=404, detail="sequence step not found")

    if body.enabled is not None:
        step.followup_enabled = body.enabled
    if body.delay_hours is not None:
        step.followup_delay_hours = body.delay_hours
    db.commit()
    return {
        "sequence_id": str(sequence_id),
        "step_no": step.step_no,
        "followup_enabled": step.followup_enabled,
        "followup_delay_hours": step.followup_delay_hours,
    }
