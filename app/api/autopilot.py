"""Autopilot launch, best time to send, and "Why isn't this sending?".

Spec: docs/features/autopilot-launch.md.

  GET  /autopilot/lawful-basis               the confirmation text + version
  GET  /strategies/{id}/autopilot            state, channels, opt-in record
  PUT  /strategies/{id}/autopilot            turn it on (lawful basis) / off
  GET  /strategies/{id}/best-time            "Messages go out at ..." per channel
  PUT  /strategies/{id}/best-time            the person's own window (or clear)
  GET  /strategies/{id}/send-diagnostics     every reason sends are not going out

Every route: the signed-in account's own strategy, else 404. Turning
Autopilot ON is a person's decision: owner or workspace manager (403 for an
SDR -- the manager-approval rule for launches must not be bypassable through
Autopilot) and never a personal API key (403). No model call in any handler.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import AutopilotOptIn
from app.db.base import get_db
from app.db.models import Product, Strategy, StrategyStatus, User
from app.services import autopilot, rbac, send_diagnostics, send_time

router = APIRouter(tags=["autopilot"])

SDR_REFUSED = ("Turning on Autopilot needs the account owner or a workspace manager: it "
               "launches outreach without a separate approval.")
API_KEY_REFUSED = ("Turning on Autopilot needs a person signed in; a personal API key cannot "
                   "confirm a lawful basis.")


def _owned_strategy(db: Session, strategy_id: uuid.UUID, current_user: User) -> Strategy:
    strategy = db.get(Strategy, strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    product = db.get(Product, strategy.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy


def _role(request: Request) -> str:
    return getattr(request.state, "workspace_role", None) or "owner"


def _actor_id(request: Request, current_user: User):
    actor = getattr(request.state, "actor", None)
    return getattr(actor, "id", None) or current_user.id


def validate_opt_in(db: Session, request: Request, body: AutopilotOptIn | None) -> None:
    """Refuse an Autopilot opt-in before anything is created or changed."""
    if body is None or not body.enabled:
        return
    if getattr(request.state, "auth_via", None) == "api_key":
        raise HTTPException(status_code=403, detail=API_KEY_REFUSED)
    if not rbac.at_least(_role(request), "manager"):
        raise HTTPException(status_code=403, detail=SDR_REFUSED)
    try:
        autopilot.check_opt_in(db, enabled=True, confirmed=body.lawful_basis_confirmed,
                               text_version=body.lawful_basis_text_version)
    except autopilot.AutopilotError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))


def record_opt_in(db: Session, request: Request, strategy: Strategy, owner: User,
                  body: AutopilotOptIn) -> None:
    try:
        autopilot.set_opt_in(db, strategy, enabled=body.enabled,
                             confirmed=body.lawful_basis_confirmed,
                             text_version=body.lawful_basis_text_version,
                             actor_id=_actor_id(request, owner), owner_id=owner.id,
                             request=request)
    except autopilot.AutopilotError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=str(exc))


@router.get("/autopilot/lawful-basis")
def get_lawful_basis(db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict:
    return {**autopilot.lawful_basis(), "available": autopilot.available(db)}


@router.get("/strategies/{strategy_id}/autopilot")
def get_autopilot(strategy_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    strategy = _owned_strategy(db, strategy_id, current_user)
    out = autopilot.view(db, strategy)
    out["can_change"] = (rbac.at_least(_role(request), "manager")
                         and getattr(request.state, "auth_via", None) != "api_key")
    return out


@router.put("/strategies/{strategy_id}/autopilot")
def put_autopilot(strategy_id: uuid.UUID, body: AutopilotOptIn, request: Request,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    """Turn Autopilot on (with the lawful-basis confirmation) or off. Both are
    audited. Turning it on for a strategy that is already verified starts it
    straight away (the 15-minute sweep would otherwise pick it up)."""
    strategy = _owned_strategy(db, strategy_id, current_user)
    if not rbac.at_least(_role(request), "manager"):
        raise HTTPException(status_code=403, detail=SDR_REFUSED)
    validate_opt_in(db, request, body)
    record_opt_in(db, request, strategy, current_user, body)
    if body.enabled and strategy.status in (StrategyStatus.VERIFIED,
                                            StrategyStatus.NEEDS_HUMAN_REVIEW,
                                            StrategyStatus.EXECUTING):
        from app.workers import autopilot_tasks  # noqa: PLC0415

        autopilot_tasks.enqueue_advance(db, strategy.id)
    return get_autopilot(strategy_id, request, db, current_user)


# --------------------------------------------------------------------------
# Best time to send
# --------------------------------------------------------------------------


class SendTimeOverrideIn(BaseModel):
    """One window for every channel, in each prospect's local time.
    `clear: true` removes it."""
    clear: bool = False
    days: list[str | int] | None = Field(default=None, max_length=7)
    start: str | None = Field(default=None, max_length=5)
    end: str | None = Field(default=None, max_length=5)


def _send_time_view(db: Session, strategy: Strategy) -> dict:
    channels = send_diagnostics._channels_in_use(db, strategy) or ["email"]
    return {
        "enabled": send_time.enabled(db),
        "override": strategy.send_time_override_json,
        "plan": strategy.send_time_plan_json,
        "timezones": send_time.timezone_coverage(db, strategy),
        "channels": [send_time.explain(db, strategy, ch) for ch in channels],
    }


@router.get("/strategies/{strategy_id}/best-time")
def get_send_time(strategy_id: uuid.UUID, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    return _send_time_view(db, _owned_strategy(db, strategy_id, current_user))


SETTINGS_REFUSED = ("Changing the sending window needs the account owner or a workspace "
                    "manager, signed in (not a personal API key).")


@router.put("/strategies/{strategy_id}/best-time")
def put_send_time(strategy_id: uuid.UUID, body: SendTimeOverrideIn, request: Request,
                  response: Response, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    """Set (202: the scheduled messages are re-placed by a background task;
    `rescheduling` is how many it will look at) or clear (200) the person's
    own sending window. Owner/manager only, never an API key. A window that
    cannot overlap the permitted hours for this strategy's leads is 422."""
    strategy = _owned_strategy(db, strategy_id, current_user)
    if (getattr(request.state, "auth_via", None) == "api_key"
            or not rbac.at_least(_role(request), "manager")):
        raise HTTPException(status_code=403, detail=SETTINGS_REFUSED)
    if body.clear:
        strategy.send_time_override_json = None
        db.commit()
        return {**_send_time_view(db, strategy), "rescheduling": 0}
    try:
        stored = send_time.validate_override(
            {"days": body.days, "start": body.start, "end": body.end})
        conflicts = send_time.override_conflicts(db, strategy, stored)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if conflicts:
        raise HTTPException(
            status_code=422,
            detail="That window never overlaps the permitted sending hours for "
                   f"{'; '.join(conflicts)}, so those messages could never be sent. "
                   "Choose a window inside them.")
    strategy.send_time_override_json = stored
    db.commit()
    from app.workers import autopilot_tasks  # noqa: PLC0415

    pending = send_time.pending_reslot_count(db, strategy)
    if pending:
        autopilot_tasks.enqueue_reslot(strategy.id)
    response.status_code = 202
    return {**_send_time_view(db, strategy), "rescheduling": pending}


class TemplateChoiceIn(BaseModel):
    whatsapp_template_id: uuid.UUID | None = None


@router.put("/strategies/{strategy_id}/autopilot/whatsapp-template")
def put_autopilot_template(strategy_id: uuid.UUID, body: TemplateChoiceIn,
                           request: Request, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)) -> dict:
    """The approved WhatsApp template Autopilot uses for this strategy (or
    none: then Autopilot's WhatsApp channel waits)."""
    strategy = _owned_strategy(db, strategy_id, current_user)
    if (getattr(request.state, "auth_via", None) == "api_key"
            or not rbac.at_least(_role(request), "manager")):
        raise HTTPException(status_code=403, detail=SETTINGS_REFUSED)
    try:
        autopilot.set_template(db, strategy, body.whatsapp_template_id)
    except autopilot.AutopilotError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc))
    return get_autopilot(strategy_id, request, db, current_user)


# --------------------------------------------------------------------------
# Why isn't this sending?
# --------------------------------------------------------------------------


@router.get("/strategies/{strategy_id}/send-diagnostics")
def get_send_diagnostics(strategy_id: uuid.UUID, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)) -> dict:
    strategy = _owned_strategy(db, strategy_id, current_user)
    out = send_diagnostics.diagnose(db, strategy)
    view = autopilot.view(db, strategy)
    out["autopilot"] = {"enabled": view["enabled"], "state": view["state"]}
    return out
