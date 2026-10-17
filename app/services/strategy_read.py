"""Read-side strategy queries shared by the REST API and the MCP connector.

Moved out of app/api/ui_support.py::list_strategies and
app/api/strategies.py::get_strategy (DECISIONS.md CONN-SERVICES), so the
Claude/ChatGPT connector (app/mcp/) reads strategies through the same
tenant-scoped code the web app does instead of a second copy of the query.
Behaviour is unchanged: the routes now call these functions and their
existing tests are the regression proof.

Tenant scoping: a strategy belongs to whoever owns its Product
(`Product.user_id`). Callers pass the principal `get_current_user` returned;
single-strategy reads take a Strategy the caller has already resolved with
crm_service.owned_strategy (404 for anyone else's).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PastClient, Product, ResearchStep, Strategy, User
from app.pipeline import budget_plan
from app.pipeline.engine import pipelines_for_flow
from app.pipeline.registry import phase_title
from app.services import usage_meter

# Every pipeline has eight phases (app/pipeline/registry.py).
PHASES = range(1, 9)


def list_owned(db: Session, user: User, *, limit: int | None = None,
               offset: int = 0) -> dict:
    """The user's strategies, newest first.

    `limit=None` returns every row -- what GET /strategies has always done
    (the web app's strategy picker shows them all). The connector always
    passes a limit.
    """
    query = (
        select(Strategy, Product.name)
        .join(Product, Product.id == Strategy.product_id)
        .where(Product.user_id == user.id)
    )
    total = int(db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one())
    query = query.order_by(Strategy.created_at.desc(), Strategy.id)
    if offset:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)
    items = [
        {
            "id": str(s.id),
            "product_id": str(s.product_id),
            "product_name": name,
            "flow_type": s.flow_type.value,
            "status": s.status.value,
            "campaign_state": s.campaign_state,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s, name in db.execute(query).all()
    ]
    return {"items": items, "total": total}


def planned_steps(strategy: Strategy) -> int:
    """How many research steps this strategy's run executes in total."""
    per_pipeline = len(budget_plan.planned_step_nos(strategy.steps_per_phase))
    return per_pipeline * len(pipelines_for_flow(strategy.flow_type))


def pipeline_status(db: Session, strategy: Strategy) -> dict:
    """Overall status + per-phase progress for every pipeline in the flow.

    The shape of app/api/schemas.py::StrategyStatusOut (enums left as enums,
    so the route can validate it into that model unchanged).
    """
    k = strategy.steps_per_phase or 9
    planned = budget_plan.planned_step_nos(strategy.steps_per_phase)
    progress: list[dict] = []
    for pipeline in pipelines_for_flow(strategy.flow_type):
        counts = dict(
            db.execute(
                select(ResearchStep.phase, func.count(ResearchStep.id))
                .where(
                    ResearchStep.strategy_id == strategy.id,
                    ResearchStep.pipeline == pipeline,
                )
                .group_by(ResearchStep.phase)
            ).all()
        )
        progress.append({
            "pipeline": pipeline.value,
            "done": sum(counts.values()),
            "total": len(planned),
            "phases": [
                {"phase": p, "title": phase_title(pipeline, p),
                 "done": counts.get(p, 0), "total": k}
                for p in PHASES
            ],
        })

    return {
        "id": strategy.id,
        "flow_type": strategy.flow_type,
        "status": strategy.status,
        "progress": progress,
        "verification": strategy.verified_passes_json or [],
        "strategy_document_ready": bool(strategy.strategy_document),
        "gtm_document_ready": bool(strategy.gtm_document),
        "error": strategy.error,
        "budget_usd": (strategy.budget_micros / 1_000_000
                       if strategy.budget_micros is not None else None),
        "spent_usd": usage_meter.spent_micros(db, strategy.id) / 1_000_000,
        "steps_per_phase": strategy.steps_per_phase,
        "planned_steps": planned_steps(strategy),
    }


def list_products(db: Session, user: User, *, limit: int, offset: int = 0) -> dict:
    """The user's products (what a strategy is created for), oldest first,
    with whether each has past clients (which picks the strategy flow) and
    how many strategies it has."""
    query = select(Product).where(Product.user_id == user.id)
    total = int(db.execute(
        select(func.count()).select_from(query.subquery())
    ).scalar_one())
    rows = db.execute(
        query.order_by(Product.created_at, Product.id).limit(limit).offset(offset)
    ).scalars().all()
    ids = [p.id for p in rows]
    past = dict(db.execute(
        select(PastClient.product_id, func.count(PastClient.id))
        .where(PastClient.product_id.in_(ids)).group_by(PastClient.product_id)
    ).all()) if ids else {}
    strategies = dict(db.execute(
        select(Strategy.product_id, func.count(Strategy.id))
        .where(Strategy.product_id.in_(ids)).group_by(Strategy.product_id)
    ).all()) if ids else {}
    items = [
        {
            "id": str(p.id),
            "name": p.name,
            "type": p.type.value,
            "business_type": p.business_type,
            "past_clients": int(past.get(p.id, 0)),
            "strategies": int(strategies.get(p.id, 0)),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in rows
    ]
    return {"items": items, "total": total}
