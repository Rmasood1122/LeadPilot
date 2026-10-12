"""Local business mode + consent-based customer win-back -- API.

Spec: docs/features/local-business-mode.md.

GET  /local-business/types                  the business types, their local B2B
                                            plays, recommended send windows and
                                            both flag states
PUT  /strategies/{id}/local-business        set / clear a strategy's service area
                                            and local offer (Part A)
POST /strategies/{id}/customers/import      import the business's OWN opted-in
                                            customers (Part B; flag
                                            customer_winback_enabled, default
                                            OFF; healthcare always refused)

The business type itself is set on the product (POST /products,
PUT /products/{id}/local-business in app/api/products.py).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import StrategyOut
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import Product, Strategy, User
from app.services import local_business as svc
from app.services.local_business import ServiceArea

router = APIRouter(tags=["local-business"])


def _owned(db: Session, strategy_id: uuid.UUID, user: User) -> tuple[Strategy, Product]:
    """404 for a strategy that is not the caller's (never 403: an id of
    another account must not be confirmed to exist)."""
    strategy = db.get(Strategy, strategy_id)
    product = db.get(Product, strategy.product_id) if strategy is not None else None
    if strategy is None or product is None or product.user_id != user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    return strategy, product


@router.get("/local-business/types")
def list_types(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    return {
        "enabled": svc.enabled(db),
        "winback_enabled": svc.winback_enabled(db),
        "types": svc.types_out(),
        "attestation": svc.ATTESTATION,
        "radius_note": ("The radius is used for research and messages. It is not "
                        "sent to the lead provider, which searches by the city or "
                        "postal code."),
    }


class LocalStrategyIn(BaseModel):
    service_area: ServiceArea | None = None
    local_offer: str | None = Field(default=None, max_length=500)


@router.put("/strategies/{strategy_id}/local-business", response_model=StrategyOut)
def set_local_context(
    strategy_id: uuid.UUID,
    body: LocalStrategyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StrategyOut:
    """Set (or, with both fields null, clear) the strategy's service area and
    offer. Affects research steps not yet run, the next lead batch and
    messages rendered from now on; nothing already sourced or sent changes."""
    from app.api.strategies import _strategy_out, local_context_or_422  # noqa: PLC0415

    strategy, product = _owned(db, strategy_id, current_user)
    area, offer = local_context_or_422(db, product, body.service_area, body.local_offer)
    strategy.service_area_json = area
    strategy.local_offer = offer
    db.commit()
    db.refresh(strategy)
    return _strategy_out(db, strategy)


@router.post("/strategies/{strategy_id}/customers/import")
async def import_customers(
    strategy_id: uuid.UUID,
    file: UploadFile = File(...),
    attestation: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Import the business's own customers, each with a recorded opt-in.

    LEGAL GUARD (docs/features/local-business-mode.md, Part B):
      * 409 CUSTOMER_WINBACK_DISABLED while the flag is off (the default);
      * 403 for a healthcare business (HIPAA -- a patient list);
      * 422 without the consent columns, with a health-data column, or
        without the exact attestation;
      * per row: refused (and NOT stored) without consent, on a channel other
        than email/WhatsApp, or when the person opted out before.
    """
    enforce_rate_limit(str(current_user.id), "customers_import", "RATE_LIMIT_LEADS_SOURCE")
    strategy, product = _owned(db, strategy_id, current_user)
    raw = await file.read(svc.MAX_IMPORT_BYTES + 1)
    try:
        return svc.import_customers(db, current_user, strategy, product, raw, attestation)
    except svc.ImportRefused as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=exc.detail)
