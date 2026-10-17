"""Create a strategy: the one code path the REST API and the connector share.

Moved out of app/api/strategies.py::create_strategy (DECISIONS.md
CONN-SERVICES) with every check in the same order: product ownership (404),
Autopilot opt-in validation, the plan's max_strategies (402) and today's AI
cap (429) via check_new_strategy_allowed, the local-business context (422),
flow inference (422), the budget plan (422), the F07 monthly forecast (429),
then the insert, the Autopilot opt-in record and the pipeline enqueue.

The checks themselves stay where Quickstart and the other callers already
import them (app/api/strategies.py, app/api/spend_guard.py,
app/api/autopilot.py); they are imported lazily, as app/services/autopilot.py
does, so this module never loads a router at import time.

The per-user rate limit (RATE_LIMIT_STRATEGIES) is NOT applied here: it must
be each caller's first statement (tests/test_rate_limit_ordering.py), so the
route and the connector tool each call enforce_rate_limit with the same
key and setting before calling create().
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import FlowType, PastClient, Product, Strategy, User
from app.workers import tasks as worker_tasks

RATE_LIMIT_SCOPE = "strategies"
RATE_LIMIT_SETTING = "RATE_LIMIT_STRATEGIES"


def create(db: Session, user: User, product_id: uuid.UUID, *,
           flow_type: FlowType | None = None, max_budget_usd: float | None = None,
           service_area=None, local_offer: str | None = None,
           autopilot=None, request: Request | None = None) -> Strategy:
    """Create a strategy and enqueue its research pipeline, or raise
    HTTPException (404/402/422/429/403) with the detail the web app shows.

    flow_type is inferred from whether the product has past clients when not
    given. Explicit with_clients on a product without past clients is
    rejected -- Flow 1 is anchored on real patterns. `autopilot` (an
    AutopilotOptIn) needs the HTTP `request` for its role and audit checks;
    the connector never passes one.
    """
    from app.api import autopilot as autopilot_api  # noqa: PLC0415
    from app.api import spend_guard as spend_guard_api  # noqa: PLC0415
    from app.api.strategies import (  # noqa: PLC0415
        check_new_strategy_allowed,
        local_context_or_422,
        plan_budget,
    )

    product = db.get(Product, product_id)
    if product is None or product.user_id != user.id:
        raise HTTPException(status_code=404, detail="product not found")

    # Autopilot launch: an opt-in is validated (lawful basis, role, flag)
    # BEFORE anything is created, so a refused opt-in leaves no strategy.
    autopilot_api.validate_opt_in(db, request, autopilot)

    # After the ownership check, so a foreign product id is 404 whatever the
    # count.
    check_new_strategy_allowed(db, user)
    service_area_json, offer = local_context_or_422(db, product, service_area, local_offer)

    has_clients = (
        db.execute(
            select(func.count(PastClient.id)).where(PastClient.product_id == product_id)
        ).scalar_one()
        > 0
    )
    if flow_type is None:
        flow_type = FlowType.WITH_CLIENTS if has_clients else FlowType.NO_CLIENTS
    elif flow_type is FlowType.WITH_CLIENTS and not has_clients:
        raise HTTPException(
            status_code=422,
            detail="flow_type=with_clients requires at least one past client "
                   "(POST /products/{id}/past-clients first)",
        )

    budget_micros, steps_per_phase = plan_budget(db, flow_type, max_budget_usd)
    # F07: forecast first; refused (429) before anything is created.
    forecast = spend_guard_api.guard_new_strategy(db, user, flow_type, steps_per_phase)
    strategy = Strategy(product_id=product.id, flow_type=flow_type,
                        budget_micros=budget_micros, steps_per_phase=steps_per_phase,
                        service_area_json=service_area_json, local_offer=offer)
    db.add(strategy)
    db.commit()
    db.refresh(strategy)
    spend_guard_api.link(db, forecast, strategy_id=strategy.id)  # F07
    if autopilot is not None and autopilot.enabled:
        autopilot_api.record_opt_in(db, request, strategy, user, autopilot)

    worker_tasks.run_pipeline.delay(str(strategy.id))
    return strategy
