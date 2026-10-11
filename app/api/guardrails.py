"""F05 Guardrails Studio -- per-account exclusion lists + per-product library.

GET    /guardrails/status                     flag state + counts
GET    /guardrails/exclusions                 this account's exclusions
POST   /guardrails/exclusions                 add one (manual)
DELETE /guardrails/exclusions/{id}            remove (soft delete)
POST   /guardrails/exclusions/import          CSV text
POST   /guardrails/exclusions/crm-sync        customers / open deals / churned
POST   /guardrails/exclusions/check           "would this be blocked?"
GET    /guardrails/products                   this account's products (library selector)
GET    /guardrails/library                    approved claims + forbidden phrases
POST   /guardrails/library                    add one
DELETE /guardrails/library/{id}               remove

TENANCY. Every handler passes current_user.id to the service, and every
service query filters on it. Another account's row answers 404, never 403,
so existence cannot be probed.

FLAG. Writes answer 409 `guardrails_disabled` while the system setting
guardrails_enabled is off -- configuring a guard that silently does nothing
is worse than being told it is off. Reads work either way.

Not plan-gated: this is a safety control (see the spec).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import Product, User
from app.services import guardrails

router = APIRouter(prefix="/guardrails", tags=["guardrails"])

_WRITE_LIMIT = "RATE_LIMIT_CRM_WRITE"


class ExclusionIn(BaseModel):
    kind: str = Field(pattern="^(domain|company|contact)$")
    value: str = Field(min_length=1, max_length=320)
    reason: str = Field(default="other", max_length=20)
    note: str | None = Field(default=None, max_length=300)


class ImportIn(BaseModel):
    csv: str = Field(min_length=1, max_length=guardrails.MAX_CSV_BYTES)
    default_reason: str = Field(default="other", max_length=20)


class CheckIn(BaseModel):
    email: str | None = Field(default=None, max_length=320)
    domain: str | None = Field(default=None, max_length=320)
    company: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    linkedin: str | None = Field(default=None, max_length=300)


class LibraryIn(BaseModel):
    kind: str = Field(pattern="^(approved_claim|forbidden_phrase)$")
    text: str = Field(min_length=2, max_length=guardrails.MAX_LIBRARY_TEXT)
    product_id: uuid.UUID | None = None
    source_url: str | None = Field(default=None, max_length=500)


def _require_enabled(db: Session) -> None:
    if not guardrails.enabled(db):
        raise HTTPException(status_code=409, detail={
            "error": "guardrails_disabled",
            "message": "Guardrails Studio is switched off for this deployment "
                       "(Admin -> System settings -> guardrails_enabled)."})


def _owned_product(db: Session, product_id: uuid.UUID, user: User) -> Product:
    product = db.get(Product, product_id)
    if product is None or product.user_id != user.id:
        raise HTTPException(status_code=404, detail="product not found")
    return product


@router.get("/status")
def status(db: Session = Depends(get_db),
           current_user: User = Depends(get_current_user)) -> dict:
    return {"enabled": guardrails.enabled(db), **guardrails.counts(db, current_user.id),
            "kinds": list(guardrails.KINDS), "reasons": list(guardrails.REASONS),
            "sources": list(guardrails.SOURCES)}


@router.get("/exclusions")
def list_exclusions(
    kind: str | None = Query(default=None, pattern="^(domain|company|contact)$"),
    source: str | None = Query(default=None, max_length=20),
    q: str | None = Query(default=None, max_length=100),
    include_removed: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return guardrails.list_exclusions(db, current_user.id, kind=kind, source=source, q=q,
                                      include_removed=include_removed, limit=limit,
                                      offset=offset)


@router.post("/exclusions", status_code=201)
def add_exclusion(body: ExclusionIn, response: Response, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "guardrails_write", _WRITE_LIMIT)
    _require_enabled(db)
    try:
        row, status_ = guardrails.add_exclusion(db, current_user.id, body.kind, body.value,
                                                reason=body.reason, note=body.note,
                                                actor_user_id=current_user.id)
    except guardrails.GuardrailValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if status_ == "exists":
        response.status_code = 200
    return {**guardrails.exclusion_out(row), "status": status_}


@router.delete("/exclusions/{exclusion_id}")
def remove_exclusion(exclusion_id: uuid.UUID, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "guardrails_write", _WRITE_LIMIT)
    _require_enabled(db)
    row = guardrails.remove_exclusion(db, current_user.id, exclusion_id,
                                      actor_user_id=current_user.id)
    if row is None:
        raise HTTPException(status_code=404, detail="exclusion not found")
    return guardrails.exclusion_out(row)


@router.post("/exclusions/import")
def import_exclusions(body: ImportIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "guardrails_write", _WRITE_LIMIT)
    _require_enabled(db)
    try:
        return guardrails.import_csv(db, current_user.id, body.csv,
                                     default_reason=body.default_reason,
                                     actor_user_id=current_user.id)
    except guardrails.GuardrailValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/exclusions/crm-sync")
def crm_sync(db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "guardrails_write", _WRITE_LIMIT)
    _require_enabled(db)
    return guardrails.sync_from_crm(db, current_user.id, actor_user_id=current_user.id)


@router.post("/exclusions/check")
def check(body: CheckIn, db: Session = Depends(get_db),
          current_user: User = Depends(get_current_user)) -> dict:
    match = guardrails.find_match(db, current_user.id, email=body.email, phone=body.phone,
                                  linkedin=body.linkedin, company=body.company,
                                  domains=[body.domain])
    return {"enabled": guardrails.enabled(db), "excluded": match is not None,
            "match": match.out() if match else None}


@router.get("/products")
def products(db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)) -> dict:
    """This account's products, for the library editor's selector (there is
    no product listing elsewhere in the API)."""
    rows = db.execute(select(Product.id, Product.name)
                      .where(Product.user_id == current_user.id)
                      .order_by(Product.created_at, Product.id)).all()
    return {"items": [{"id": str(pid), "name": name} for pid, name in rows]}


@router.get("/library")
def list_library(product_id: uuid.UUID | None = None, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    if product_id is not None:
        _owned_product(db, product_id, current_user)
    return {"product_id": str(product_id) if product_id else None,
            "items": guardrails.list_library(db, current_user.id, product_id)}


@router.post("/library", status_code=201)
def add_library_entry(body: LibraryIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "guardrails_write", _WRITE_LIMIT)
    _require_enabled(db)
    if body.product_id is not None:
        _owned_product(db, body.product_id, current_user)
    try:
        row = guardrails.add_library_entry(db, current_user.id, body.kind, body.text,
                                           product_id=body.product_id,
                                           source_url=body.source_url,
                                           actor_user_id=current_user.id)
    except guardrails.GuardrailValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return guardrails.library_out(row)


@router.delete("/library/{entry_id}", status_code=204)
def remove_library_entry(entry_id: uuid.UUID, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)) -> Response:
    enforce_rate_limit(str(current_user.id), "guardrails_write", _WRITE_LIMIT)
    _require_enabled(db)
    if not guardrails.remove_library_entry(db, current_user.id, entry_id,
                                           actor_user_id=current_user.id):
        raise HTTPException(status_code=404, detail="library entry not found")
    return Response(status_code=204)
