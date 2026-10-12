"""Intake flow — products and past clients (Flow 1's "yes" path)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.metering import metered
from app.api.schemas import (
    PastClientOut,
    PastClientsCreate,
    ProductCreate,
    ProductOut,
)
from app.db.base import get_db
from app.db.models import PastClient, Product, User
from app.services.local_business import BusinessTypeKey
from app.services.pattern_recognition import extract_patterns

router = APIRouter(prefix="/products", tags=["intake"])


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    body: ProductCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Product:
    """Step 1 of intake: the user submits a product or skill.

    Owner is the authenticated user (JWT) — NOT body.user_email. The field
    stays on ProductCreate for backward-compat with the CLI/SDK (M6), but is
    ignored when it doesn't match the token holder, so one logged-in user
    can never create a product under another user's account by passing a
    different email in the body.
    """
    if body.business_type is not None:
        from app.services import local_business  # noqa: PLC0415

        if not local_business.enabled(db):
            raise HTTPException(status_code=422, detail=local_business.LOCAL_MODE_DISABLED)
    product = Product(
        id=uuid.uuid4(),
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        type=body.type,
    )
    db.add(product)
    if body.business_type is not None:
        from app.services import local_business  # noqa: PLC0415

        # Audited like every later change (who, from, to) and sets the
        # healthcare lock when the product starts as healthcare.
        local_business.change_business_type(db, product, body.business_type,
                                            actor=current_user, request=request)
    db.commit()
    db.refresh(product)
    return product


@router.get("/{product_id}", response_model=ProductOut)
def get_product(
    product_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Product:
    product = db.get(Product, product_id)
    if product is None or product.user_id != current_user.id:
        # 404 (not 403) so an attacker can't tell "exists but not yours"
        # from "doesn't exist" — standard ownership-check practice.
        raise HTTPException(status_code=404, detail="product not found")
    return product


class LocalBusinessTypeIn(BaseModel):
    business_type: BusinessTypeKey | None = Field(
        description="restaurant | healthcare | retail | local_service | other; "
                    "null = not a local business")


@router.put("/{product_id}/local-business", response_model=ProductOut)
def set_business_type(
    product_id: uuid.UUID,
    body: LocalBusinessTypeIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Product:
    """Local business mode: set or clear the product's business type.

    Every change is audited (security_audit_events: who, from, to). Healthcare
    rules (local_business.change_business_type): a product holding imported
    customers can neither become nor stop being healthcare (409), and a
    product that was ever healthcare keeps customer win-back refused."""
    product = db.get(Product, product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="product not found")
    from app.services import local_business  # noqa: PLC0415

    if body.business_type is not None and not local_business.enabled(db):
        raise HTTPException(status_code=422, detail=local_business.LOCAL_MODE_DISABLED)
    try:
        local_business.change_business_type(db, product, body.business_type,
                                            actor=current_user, request=request)
    except local_business.ImportRefused as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status, detail=exc.detail)
    db.commit()
    db.refresh(product)
    return product


@router.post(
    "/{product_id}/past-clients",
    response_model=list[PastClientOut],
    status_code=201,
)
def add_past_clients(
    product_id: uuid.UUID,
    body: PastClientsCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PastClient]:
    """Step 2, "yes" path: past-client details + acquisition stories.

    Each client's text is sent through the pattern-recognition service
    (Claude) and the structured patterns are stored alongside the raw
    text. Extraction failures are stored as null patterns and never block
    intake."""
    product = db.get(Product, product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="product not found")

    with metered(db, current_user, "intake", refuse_after=False):
        created: list[PastClient] = []
        for item in body.clients:
            patterns = extract_patterns(item.details, item.acquisition_story)
            created.append(
                PastClient(
                    product_id=product.id,
                    details=item.details,
                    acquisition_story=item.acquisition_story,
                    extracted_patterns_json=patterns,
                )
            )
        db.add_all(created)
        db.commit()
        for c in created:
            db.refresh(c)
        return created