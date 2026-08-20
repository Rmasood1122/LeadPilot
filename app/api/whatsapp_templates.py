"""WhatsApp template APIs — Milestone 4, Chunk 2.

POST   /whatsapp/templates                — create a draft (validated)
GET    /whatsapp/templates                — list (newest first)
GET    /whatsapp/templates/{id}           — one template
PUT    /whatsapp/templates/{id}           — edit draft/rejected in place;
                                            editing APPROVED creates a new
                                            draft version (immutability)
POST   /whatsapp/templates/{id}/submit    — submit to Meta review
POST   /whatsapp/templates/{id}/sync      — pull status from Meta
POST   /whatsapp/templates/generate       — Claude-drafted candidates from
                                            a strategy's Phase 2 + 6
                                            research (saved as DRAFTS only,
                                            never auto-submitted)

Lifecycle: draft -> submitted -> approved | rejected(-> edit -> draft).
Only APPROVED templates are sendable — enforced in the adapter's send()
guard, not just here.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.base import get_db
from app.db.models import (
    Product,
    Strategy,
    User,
    WhatsAppTemplate,
    WhatsAppTemplateCategory,
)
from app.integrations.whatsapp import (
    WhatsAppChannel,
    WhatsAppNotConfigured,
)
from app.services import whatsapp_templates as svc
from app.services.whatsapp_templates import TemplateError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsapp/templates", tags=["whatsapp"])


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class TemplateCreate(BaseModel):
    name: str = Field(..., description="lowercase_snake_case, e.g. intro_offer_v1")
    language: str = Field(..., description="e.g. en_US")
    category: WhatsAppTemplateCategory = WhatsAppTemplateCategory.MARKETING
    body: str = Field(..., description="Body text with sequential {{1}}.. placeholders")
    variable_descriptions: dict[str, str] = Field(
        default_factory=dict,
        description='What each placeholder means, e.g. {"1": "first name"}',
    )


class TemplateUpdate(BaseModel):
    body: str | None = None
    category: WhatsAppTemplateCategory | None = None
    variable_descriptions: dict[str, str] | None = None


class GenerateRequest(BaseModel):
    strategy_id: uuid.UUID


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _get_or_404(template_id: uuid.UUID, db: Session) -> WhatsAppTemplate:
    row = db.get(WhatsAppTemplate, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="template not found")
    return row


def _adapter(db: Session) -> WhatsAppChannel:
    try:
        return WhatsAppChannel(session=db)
    except WhatsAppNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# --------------------------------------------------------------------------
# Routes
#
# NOTE on auth model here: WhatsAppTemplate has no user_id/strategy_id
# column — it is a genuinely deployment-wide resource (one Meta WhatsApp
# Business Account per self-hosted install, shared by every account on
# it), so these routes require LOGIN (get_current_user) but are
# deliberately NOT owner-scoped to a single user, unlike products/
# strategies/leads/sequences/analytics. The one exception is
# generate_templates, which reads a specific strategy's private Phase 2/6
# research to draft candidates — that strategy_id IS ownership-checked.
# --------------------------------------------------------------------------


@router.post("", status_code=201)
def create_template(
    body: TemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        row = svc.create_draft(
            db,
            name=body.name,
            language=body.language,
            category=body.category,
            body=body.body,
            variable_descriptions=body.variable_descriptions,
        )
    except TemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return svc.serialize(row)


@router.get("")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = db.execute(
        select(WhatsAppTemplate).order_by(WhatsAppTemplate.created_at.desc())
    ).scalars().all()
    return {"templates": [svc.serialize(r) for r in rows]}


@router.get("/{template_id}")
def get_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    return svc.serialize(_get_or_404(template_id, db))


@router.put("/{template_id}")
def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    row = _get_or_404(template_id, db)
    try:
        updated = svc.update_template(
            db, row,
            body=body.body,
            category=body.category,
            variable_descriptions=body.variable_descriptions,
        )
    except TemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    result = svc.serialize(updated)
    if updated.id != row.id:
        result["note"] = (
            "approved templates are immutable — a new draft version was "
            "created instead of editing in place"
        )
    return result


@router.post("/{template_id}/submit")
def submit_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    row = _get_or_404(template_id, db)
    try:
        updated = svc.submit_template(db, row, adapter=_adapter(db))
    except TemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return svc.serialize(updated)


@router.post("/{template_id}/sync")
def sync_template(
    template_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    row = _get_or_404(template_id, db)
    try:
        updated = svc.sync_template(db, row, adapter=_adapter(db))
    except TemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return svc.serialize(updated)


@router.post("/generate", status_code=201)
def generate_templates(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Unlike the other routes in this file, this one DOES need an
    # ownership check — it reads a specific strategy's private Phase 2/6
    # research to draft candidates, and that strategy belongs to one user.
    strategy = db.get(Strategy, body.strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="strategy not found")
    product = db.get(Product, strategy.product_id)
    if product is None or product.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="strategy not found")
    try:
        rows = svc.generate_drafts(db, strategy)
    except TemplateError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "templates": [svc.serialize(r) for r in rows],
        "note": (
            "drafts only — review each candidate, edit if needed, then "
            "submit explicitly via POST /whatsapp/templates/{id}/submit. "
            "Nothing is auto-submitted."
        ),
    }