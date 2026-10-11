"""F07 -- Spend Guard + Cost Forecast endpoints and the pre-run guard.

GET  /spend-guard/usage            the usage page: month spend vs cap, credits,
                                   alerts, verified results vs attempt cost,
                                   recent forecasts with forecast-vs-actual
PUT  /spend-guard/cap              set / clear the monthly cap (owner/manager)
POST /spend-guard/forecast         preview a run's forecast (stores nothing)
GET  /spend-guard/forecasts/{id}   one forecast with its reconciliation

The guard_* helpers are what the run endpoints (strategies, lead sourcing,
Quickstart) call BEFORE they create or enqueue anything: forecast, store the
forecast, and refuse with 429 `monthly_spend_cap_reached` when it does not fit
in what is left of the month. With the flag off they return None and do
nothing at all.

No route here calls a model, sends anything, or reads another account's rows:
every query filters by the caller's id (strategies through _owned_strategy).
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import FlowType, ResearchStep, Strategy, User
from app.services import rbac, spend_guard

router = APIRouter(tags=["spend-guard"])

DISABLED_DETAIL = "Spend Guard is disabled by the administrator"
MIN_CAP_USD = 1.0
MAX_CAP_USD = 1_000_000.0


def _require_enabled(db: Session) -> None:
    if not spend_guard.enabled(db):
        raise HTTPException(status_code=409, detail=DISABLED_DETAIL)


# --------------------------------------------------------------------------
# The pre-run guard (called from strategies.py, leads.py, quickstart.py)
# --------------------------------------------------------------------------


def _guard(db: Session, user: User, make_forecast, *, strategy_id=None):
    """Forecast, store, refuse if it does not fit. None when the flag is off.

    Allowed: the forecast row is added WITHOUT a commit, so it is saved by the
    endpoint's own commit -- and disappears with everything else if the
    request fails a later check. Refused: the request's pending changes are
    rolled back (a refused run changes nothing), the refused forecast is
    committed as the audit record, alerts are evaluated, then 429."""
    if not spend_guard.enabled(db):
        return None
    decision = spend_guard.evaluate(db, user.id, make_forecast())
    if decision.allowed:
        return spend_guard.record(db, user.id, decision, strategy_id=strategy_id,
                                  commit=False)
    db.rollback()
    spend_guard.record(db, user.id, decision, strategy_id=strategy_id)
    try:
        # The cap is stopping work: the 100% alert fires (once per month).
        spend_guard.evaluate_alerts(db, user.id, force_cap_reached=True)
    except Exception:  # noqa: BLE001 -- an alert must never decide a run
        db.rollback()
    raise HTTPException(status_code=429, detail=decision.refusal())


def guard_new_strategy(db: Session, user: User, flow_type: FlowType,
                       steps_per_phase: int | None):
    return _guard(db, user, lambda: spend_guard.forecast_strategy_run(
        db, flow_type=flow_type, steps_per_phase=steps_per_phase))


def _done_steps(db: Session, strategy: Strategy) -> int:
    return int(db.execute(select(func.count(ResearchStep.id)).where(
        ResearchStep.strategy_id == strategy.id)).scalar_one() or 0)


def guard_strategy_resume(db: Session, user: User, strategy: Strategy):
    """A resume runs only the planned steps not done yet, then verification."""
    return _guard(db, user, lambda: spend_guard.forecast_strategy_run(
        db, flow_type=strategy.flow_type, steps_per_phase=strategy.steps_per_phase,
        done_steps=_done_steps(db, strategy),
        market_intel_pending=strategy.market_signals_fetched_at is None),
        strategy_id=strategy.id)


def guard_strategy_reverify(db: Session, user: User, strategy: Strategy):
    return _guard(db, user, lambda: spend_guard.forecast_strategy_run(
        db, flow_type=strategy.flow_type, steps_per_phase=strategy.steps_per_phase,
        include_pipeline=False), strategy_id=strategy.id)


def guard_enrichment_run(db: Session, user: User, strategy: Strategy, requested: int):
    return _guard(db, user, lambda: spend_guard.forecast_enrichment_run(
        db, user.id, requested), strategy_id=strategy.id)


def guard_quickstart(db: Session, user: User, steps_per_phase: int | None):
    from app.services import quickstart  # noqa: PLC0415

    return _guard(db, user, lambda: spend_guard.forecast_quickstart(
        db, user.id, steps_per_phase=steps_per_phase,
        requested_leads=quickstart.lead_target(db),
        budget_micros=quickstart.budget_micros(db)))


def link(db: Session, row, *, strategy_id=None, batch_id=None) -> None:
    spend_guard.link(db, row, strategy_id=strategy_id, batch_id=batch_id)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@router.get("/spend-guard/usage")
def get_usage(db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)) -> dict:
    _require_enabled(db)
    return spend_guard.usage(db, current_user)


class CapIn(BaseModel):
    #: USD per UTC calendar month; null removes the monthly cap.
    monthly_cap_usd: float | None = Field(default=None)
    email_alerts: bool = True


@router.put("/spend-guard/cap")
def set_cap(body: CapIn, request: Request, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)) -> dict:
    """Owner or manager only: the cap decides what every member can run."""
    _require_enabled(db)
    role = getattr(request.state, "workspace_role", None) or "owner"
    if not rbac.at_least(role, "manager"):
        raise HTTPException(status_code=403,
                            detail="Changing the spend cap needs an owner or manager.")
    cap = body.monthly_cap_usd
    if cap is not None and not (MIN_CAP_USD <= cap <= MAX_CAP_USD):
        raise HTTPException(status_code=422,
                            detail=f"monthly_cap_usd must be between ${MIN_CAP_USD:.2f} "
                                   f"and ${MAX_CAP_USD:,.0f}, or null for no cap")
    actor = getattr(getattr(request.state, "actor", None), "id", None) or current_user.id
    spend_guard.set_cap(db, current_user.id, cap_usd=cap, email_alerts=body.email_alerts,
                        actor_id=actor)
    spend_guard.evaluate_alerts(db, current_user.id)
    return spend_guard.usage(db, current_user)


class ForecastIn(BaseModel):
    kind: Literal["strategy_run", "enrichment_run"]
    flow_type: FlowType | None = None
    max_budget_usd: float | None = None
    strategy_id: uuid.UUID | None = None
    max_leads: int | None = Field(default=None, ge=1)


@router.post("/spend-guard/forecast")
def preview_forecast(body: ForecastIn, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict:
    """What a run would cost and whether the cap would let it start. Stores
    nothing and starts nothing."""
    from app.api.leads import _owned_strategy  # noqa: PLC0415
    from app.api.strategies import plan_budget  # noqa: PLC0415
    from app.config import settings  # noqa: PLC0415
    from app.workers import lead_tasks  # noqa: PLC0415

    _require_enabled(db)
    if body.kind == spend_guard.STRATEGY_RUN:
        if body.flow_type is None:
            raise HTTPException(status_code=422, detail="flow_type is required")
        _, steps_per_phase = plan_budget(db, body.flow_type, body.max_budget_usd)
        forecast = spend_guard.forecast_strategy_run(
            db, flow_type=body.flow_type, steps_per_phase=steps_per_phase)
    else:
        if body.strategy_id is None:
            raise HTTPException(status_code=422, detail="strategy_id is required")
        strategy = _owned_strategy(db, body.strategy_id, current_user)
        room = lead_tasks.strategy_lead_room(db, strategy.id)
        requested = min(body.max_leads or settings.leads_max_per_run,
                        settings.leads_max_per_run,
                        room if room is not None else settings.leads_max_per_run)
        forecast = spend_guard.forecast_enrichment_run(db, current_user.id, max(requested, 0))
    return spend_guard.evaluate(db, current_user.id, forecast).out()


@router.get("/spend-guard/forecasts/{forecast_id}")
def get_forecast(forecast_id: uuid.UUID, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    _require_enabled(db)
    row = spend_guard.owned_forecast(db, forecast_id, current_user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="forecast not found")
    return spend_guard.reconcile(db, row)
