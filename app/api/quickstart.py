"""F06 Quickstart -- website URL + one-line offer -> review-only first drafts.

GET  /quickstart/config                  is it on; lead target; budget; label
POST /quickstart                         start a run (creates product + strategy,
                                         starts the full pipeline AND Quickstart)
GET  /quickstart                         the caller's recent runs
GET  /quickstart/{run_id}                one run with its drafts
POST /quickstart/drafts/{id}/discard     review feedback; nothing else changes
GET  /admin/quickstart/timing            admin: p50/p90 time to first draft

Behind the `quickstart_enabled` system setting (default off): with it off,
every route but /quickstart/config answers 404.

NOTHING HERE SENDS. There is deliberately no approve/send/schedule route: a
draft is reviewed, copied or discarded. Outreach to these leads happens only
through the verified strategy's sequence, through every normal gate. See
docs/features/f06-quickstart.md.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.api.strategies import check_new_strategy_allowed, plan_budget
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import (
    FlowType, Lead, Product, ProductType, QuickstartRun, Strategy, User,
)
from app.services import quickstart, safe_fetch

router = APIRouter(tags=["quickstart"])

NOT_ENABLED = "Quickstart is not enabled on this deployment"


class QuickstartIn(BaseModel):
    """Validated by FastAPI BEFORE the handler runs, so a malformed or unsafe
    URL is a free 422 and never costs a rate-limit slot."""

    website_url: str = Field(min_length=3, max_length=safe_fetch.MAX_URL_LENGTH)
    offer: str = Field(min_length=1, max_length=1000)
    product_name: str | None = Field(default=None, max_length=200)

    @field_validator("website_url")
    @classmethod
    def _url(cls, value: str) -> str:
        # SSRF, shape only (no network here): https/443, no credentials, no
        # internal host names, no private/loopback/link-local IP literals. The
        # worker re-resolves and re-checks every hop before fetching.
        return safe_fetch.validate_url(value)

    @field_validator("offer")
    @classmethod
    def _offer(cls, value: str) -> str:
        return quickstart.clean_offer(value)


def require_enabled(db: Session = Depends(get_db)) -> None:
    """404 while `quickstart_enabled` is off. A dependency, so it answers
    before the handler body (and its rate limit) runs."""
    if not quickstart.enabled(db):
        raise HTTPException(status_code=404, detail=NOT_ENABLED)


@router.get("/quickstart/config")
def quickstart_config(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    return quickstart.config(db)


# Rate limited with the STRATEGIES bucket: this creates a strategy and starts
# its full 144-step pipeline, exactly what RATE_LIMIT_STRATEGIES governs.
@router.post("/quickstart", status_code=202, dependencies=[Depends(require_enabled)])
def create_quickstart(body: QuickstartIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    """Start a Quickstart run. Review-only output; nothing is ever sent."""
    enforce_rate_limit(str(current_user.id), "strategies", "RATE_LIMIT_STRATEGIES")
    url, offer = body.website_url, body.offer

    # The same account checks as POST /products/{id}/strategies, BEFORE any row
    # is written, so a refusal leaves no orphan product behind.
    check_new_strategy_allowed(db, current_user)
    budget_micros, steps_per_phase = plan_budget(db, FlowType.NO_CLIENTS, None)

    product = Product(user_id=current_user.id,
                      name=quickstart.product_name_for(url, body.product_name),
                      description=f"{offer}\n\nWebsite: {url}",
                      type=ProductType.PRODUCT)
    db.add(product)
    db.flush()
    strategy = Strategy(product_id=product.id, flow_type=FlowType.NO_CLIENTS,
                        budget_micros=budget_micros, steps_per_phase=steps_per_phase)
    db.add(strategy)
    db.flush()
    run = QuickstartRun(user_id=current_user.id, product_id=product.id,
                        strategy_id=strategy.id, website_url=url, offer=offer,
                        status=quickstart.QUEUED,
                        lead_target=quickstart.lead_target(db),
                        budget_micros=quickstart.budget_micros(db))
    db.add(run)
    db.commit()
    db.refresh(run)

    # The full pipeline: unchanged, and what supersedes the drafts.
    from app.workers import quickstart_tasks, tasks as worker_tasks  # noqa: PLC0415

    worker_tasks.run_pipeline.delay(str(strategy.id))
    if not quickstart_tasks.enqueue(run.id):
        run.status = quickstart.FAILED
        run.error = "Quickstart could not be queued; the full research pipeline was started"
        db.commit()
        raise HTTPException(status_code=503, detail=run.error)
    return quickstart.run_out(db, run)


@router.get("/quickstart", dependencies=[Depends(require_enabled)])
def list_quickstarts(db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict:
    runs = quickstart.list_runs(db, current_user.id)
    for run in runs:
        quickstart.refresh_superseded(db, run)
    return {"items": [quickstart.run_out(db, run) for run in runs]}


@router.get("/quickstart/{run_id}", dependencies=[Depends(require_enabled)])
def get_quickstart(run_id: uuid.UUID, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    run = quickstart.owned_run(db, run_id, current_user.id)
    if run is None:
        raise HTTPException(status_code=404, detail="quickstart run not found")
    quickstart.refresh_superseded(db, run)
    return quickstart.run_out(db, run, drafts=True)


@router.post("/quickstart/drafts/{draft_id}/discard",
             dependencies=[Depends(require_enabled)])
def discard_draft(draft_id: uuid.UUID, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    draft = quickstart.owned_draft(db, draft_id, current_user.id)
    if draft is None:
        raise HTTPException(status_code=404, detail="draft not found")
    draft.status = quickstart.DISCARDED
    db.commit()
    run = db.get(QuickstartRun, draft.run_id)
    return quickstart.draft_out(draft, db.get(Lead, draft.lead_id),
                                superseded=bool(run and run.superseded_at))


@router.get("/admin/quickstart/timing")
def quickstart_timing(days: int = Query(default=30, ge=1, le=365),
                      db: Session = Depends(get_db),
                      _admin: User = Depends(require_admin)) -> dict:
    """The success metric's measurement: time from request to first
    reviewable draft. Deployment-wide aggregate; no per-account rows."""
    return quickstart.timing_summary(db, days=days)
