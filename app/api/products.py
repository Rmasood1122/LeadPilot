"""Intake flow — products and past clients (Flow 1's "yes" path)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.schemas import (
    PastClientOut,
    PastClientsCreate,
    ProductCreate,
    ProductOut,
)
from app.db.base import get_db
from app.db.models import PastClient, Product, User
from app.services.pattern_recognition import extract_patterns

router = APIRouter(prefix="/products", tags=["intake"])


@router.post("", response_model=ProductOut, status_code=201)
def create_product(
    body: ProductCreate,
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
    product = Product(
        user_id=current_user.id,
        name=body.name,
        description=body.description,
        type=body.type,
    )
    db.add(product)
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