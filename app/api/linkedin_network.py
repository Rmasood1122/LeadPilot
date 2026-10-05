"""Private LinkedIn network (Growth plan and up).

Every query below is filtered on current_user.id. There is no endpoint, flag or
parameter that reads another account's connections.
"""

from __future__ import annotations

import uuid
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.plans import PLANS, PlanLimitExceeded, plan_limit_response
from app.db.base import get_db
from app.db.models import (
    LinkedInConnection, LinkedInConnectionMatch, LinkedInImport, Product, User,
)
from app.services import linkedin_network as ln
from app.services import security_audit

router = APIRouter(prefix="/linkedin-network", tags=["linkedin-network"])

UPGRADE_TO = "growth"


class ImportIn(BaseModel):
    csv_text: str = Field(min_length=1, description="Contents of LinkedIn's Connections.csv")


def _require_plan(user: User) -> None:
    if ln.is_eligible(user):
        return
    plan = getattr(user.plan, "value", user.plan) or "free"
    raise HTTPException(status_code=402, detail=plan_limit_response(PlanLimitExceeded(
        limit_key="linkedin_network", current_plan=plan, upgrade_to=UPGRADE_TO,
        message=f"{PLANS.get(plan, PLANS['free'])['display_name']} plan does not include "
                "the LinkedIn network. Upgrade to Growth or higher.")))


@router.get("/status")
def status(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    """Readable on every plan, so the page can explain the upgrade."""
    plan = getattr(current_user.plan, "value", current_user.plan) or "free"
    last_import = db.execute(select(func.max(LinkedInImport.created_at))
                             .where(LinkedInImport.user_id == current_user.id)).scalar_one()
    last_analyzed = db.execute(select(func.max(LinkedInConnectionMatch.analyzed_at))
                               .where(LinkedInConnectionMatch.user_id == current_user.id)
                               ).scalar_one()
    count = db.execute(select(func.count(LinkedInConnection.id))
                       .where(LinkedInConnection.user_id == current_user.id)).scalar_one()
    return {
        "eligible": ln.is_eligible(current_user), "plan": plan,
        "upgrade_to": None if ln.is_eligible(current_user) else UPGRADE_TO,
        "connection_count": count,
        "last_import_at": last_import, "last_analyzed_at": last_analyzed,
        "needs_new_export": ln.needs_new_export(db, current_user),
        "max_bytes": ln.MAX_BYTES, "max_rows": ln.MAX_ROWS,
    }


@router.post("/import")
def import_export(body: ImportIn, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    _require_plan(current_user)
    if len(body.csv_text.encode("utf-8")) > ln.MAX_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"File is larger than {ln.MAX_BYTES // 1_000_000} MB.")
    try:
        parsed = ln.parse_connections_csv(body.csv_text)
    except ln.NetworkImportError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    out = ln.import_connections(db, current_user, parsed)
    analysis = ln.analyze_user(db, current_user)
    # Counts only: never names, companies or addresses.
    security_audit.record(db, action=security_audit.LINKEDIN_NETWORK_IMPORTED,
                          request=request, user_id=current_user.id,
                          target_type="linkedin_network", details=out)
    db.commit()
    return {**out, "matched": analysis["matches"]}


@router.post("/analyze")
def analyze(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    _require_plan(current_user)
    return ln.analyze_user(db, current_user)


@router.get("/recommendations")
def recommendations(
    product_id: uuid.UUID | None = None,
    min_score: int = Query(default=ln.MATCH_THRESHOLD, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_plan(current_user)
    q = select(Product).where(Product.user_id == current_user.id).order_by(Product.created_at)
    if product_id:
        q = q.where(Product.id == product_id)
    out = []
    for product in db.execute(q).scalars().all():
        rows = db.execute(
            select(LinkedInConnectionMatch, LinkedInConnection)
            .join(LinkedInConnection, LinkedInConnection.id == LinkedInConnectionMatch.connection_id)
            .where(LinkedInConnectionMatch.user_id == current_user.id,
                   LinkedInConnection.user_id == current_user.id,
                   LinkedInConnectionMatch.product_id == product.id,
                   LinkedInConnectionMatch.score >= min_score)
            .order_by(LinkedInConnectionMatch.score.desc(), LinkedInConnection.full_name)
        ).all()
        segments = Counter(match.segment for match, _ in rows)
        out.append({
            "product_id": str(product.id), "product_name": product.name,
            "total_matches": len(rows),
            "segments": [{"segment": s, "count": n} for s, n in segments.most_common()],
            "matches": [{
                "connection_id": str(c.id), "full_name": c.full_name,
                "position": c.position, "company": c.company,
                "profile_url": c.profile_url, "connected_on": c.connected_on,
                "score": match.score, "segment": match.segment,
                "reasons": match.reasons_json,
            } for match, c in rows[:limit]],
        })
    return {"products": out}


@router.delete("")
def erase(request: Request, db: Session = Depends(get_db),
          current_user: User = Depends(get_current_user)) -> dict:
    """Delete everything this account uploaded. Never plan-gated: a downgraded
    account can always remove its data."""
    out = ln.erase_user_network(db, current_user)
    security_audit.record(db, action=security_audit.LINKEDIN_NETWORK_ERASED,
                          request=request, user_id=current_user.id,
                          target_type="linkedin_network", details=out)
    db.commit()
    return out
