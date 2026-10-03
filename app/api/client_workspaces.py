"""Founder / agency mode: per-client workspaces (Part 1, Feature 11).

GET    /clients                          every client, with its numbers
POST   /clients                          add one
GET    /clients/{id}                     one client
PATCH  /clients/{id}                     rename, re-price, pause, archive
GET    /clients/{id}/report              reporting scoped to this client only
GET    /clients/{id}/billing             what this client owes, with the working
POST   /clients/{id}/domains             add a sending domain to its pool
DELETE /clients/{id}/domains/{domain}    remove one
POST   /strategies/{id}/client           assign a campaign to a client (or none)

`/clients` is a new prefix. `/strategies/{id}/client` is a new sub-path under
strategies.py's `/strategies/{id}`.

Everything is scoped to the CALLER'S TEAM WORKSPACE (the X-Workspace-Id header,
resolved the way every other workspace-aware route resolves it), so a client
belonging to another agency is a 404 rather than a 403 -- its existence must not
be probeable.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.analytics import _owned_strategy
from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import ClientWorkspace, User
from app.services import client_workspaces, rbac, workspaces

router = APIRouter(tags=["clients"])


class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    billing_email: str | None = Field(default=None, max_length=320)
    billing_reference: str | None = Field(default=None, max_length=100)
    #: Money is integer cents everywhere in this schema -- see Deal.value_cents.
    monthly_fee_cents: int | None = Field(default=None, ge=0)
    per_meeting_fee_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = None


class ClientPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|paused|archived)$")
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=320)
    billing_email: str | None = Field(default=None, max_length=320)
    billing_reference: str | None = Field(default=None, max_length=100)
    monthly_fee_cents: int | None = Field(default=None, ge=0)
    per_meeting_fee_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    notes: str | None = None


class DomainIn(BaseModel):
    domain: str = Field(min_length=4, max_length=253)
    note: str | None = Field(default=None, max_length=200)


class AssignIn(BaseModel):
    #: null moves the campaign back to the agency's own work, which is a real
    #: state and not an error.
    client_id: uuid.UUID | None = None


def _context(request: Request, db: Session, current_user: User) -> workspaces.Context:
    return workspaces.context_for_request(request, db, current_user)


def _client(request: Request, db: Session, current_user: User,
            client_id: uuid.UUID) -> ClientWorkspace:
    ctx = _context(request, db, current_user)
    client = client_workspaces.owned(db, ctx.workspace, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    return client


def _require_manager(request: Request, db: Session, current_user: User) -> None:
    """Pricing and domain pools are decisions, not data entry: an SDR should
    not be able to re-price a client or point their sending at a new domain."""
    ctx = _context(request, db, current_user)
    if not rbac.at_least(ctx.role, "manager"):
        raise HTTPException(status_code=403,
                            detail="Managing clients needs a manager in this workspace.")


@router.get("/clients")
def list_clients(request: Request, include_archived: bool = Query(default=False),
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    """Every client with its own numbers, plus the campaigns assigned to none.

    The unassigned bucket is shown rather than hidden: work that belongs to
    nobody is exactly the work that stops being invoiced."""
    ctx = _context(request, db, current_user)
    overview = client_workspaces.overview(db, ctx.workspace, current_user.id)
    if include_archived:
        overview["archived"] = [
            client_workspaces.client_out(db, client)
            for client in client_workspaces.clients(db, ctx.workspace,
                                                    include_archived=True)
            if client.status == client_workspaces.ARCHIVED]
    return overview


@router.post("/clients", status_code=201)
def create_client(body: ClientIn, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "client_write", "RATE_LIMIT_CRM_WRITE")
    _require_manager(request, db, current_user)
    ctx = _context(request, db, current_user)
    try:
        client = client_workspaces.create(db, ctx.workspace,
                                          **body.model_dump(exclude_none=True))
    except client_workspaces.ClientError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return client_workspaces.client_out(db, client)


@router.get("/clients/{client_id}")
def get_client(client_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    client = _client(request, db, current_user, client_id)
    return {**client_workspaces.client_out(db, client),
            **client_workspaces.report(db, client)}


@router.patch("/clients/{client_id}")
def patch_client(client_id: uuid.UUID, body: ClientPatch, request: Request,
                 db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "client_write", "RATE_LIMIT_CRM_WRITE")
    _require_manager(request, db, current_user)
    client = _client(request, db, current_user, client_id)
    try:
        client_workspaces.update(db, client, body.model_dump(exclude_none=True))
    except client_workspaces.ClientError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return client_workspaces.client_out(db, client)


@router.get("/clients/{client_id}/report")
def client_report(client_id: uuid.UUID, request: Request,
                  db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    """Reporting over THIS client's campaigns only -- scoped at the query, so
    there is no filtering step anyone can forget."""
    client = _client(request, db, current_user, client_id)
    return client_workspaces.report(db, client)


@router.get("/clients/{client_id}/billing")
def client_billing(client_id: uuid.UUID, request: Request,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    """What this client owes this month, with the working.

    A retainer plus a per-meeting fee times a meeting count is an invoice a
    client will query, and an agency that cannot show the count loses the
    argument."""
    client = _client(request, db, current_user, client_id)
    return client_workspaces.billing_view(db, client)


@router.post("/clients/{client_id}/domains", status_code=201)
def add_client_domain(client_id: uuid.UUID, body: DomainIn, request: Request,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    """Reserve a sending domain for this client.

    Enforced in the send path, not just here. An empty pool means no
    restriction, so adding the FIRST domain is the moment this client's
    campaigns become restricted to it."""
    _require_manager(request, db, current_user)
    client = _client(request, db, current_user, client_id)
    try:
        client_workspaces.add_domain(db, client, body.domain, body.note)
    except client_workspaces.ClientError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return client_workspaces.client_out(db, client)


@router.delete("/clients/{client_id}/domains/{domain}")
def remove_client_domain(client_id: uuid.UUID, domain: str, request: Request,
                         db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)) -> dict:
    _require_manager(request, db, current_user)
    client = _client(request, db, current_user, client_id)
    if not client_workspaces.remove_domain(db, client, domain):
        raise HTTPException(status_code=404, detail="that domain is not in this pool")
    return client_workspaces.client_out(db, client)


@router.post("/strategies/{strategy_id}/client")
def assign_strategy_client(strategy_id: uuid.UUID, body: AssignIn, request: Request,
                           db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)) -> dict:
    """File a campaign under a client, or move it back to the agency's own work.

    Allowed while the campaign is running: an agency that wins a client
    mid-flight should not have to stop outreach to file it correctly."""
    enforce_rate_limit(str(current_user.id), "client_write", "RATE_LIMIT_CRM_WRITE")
    strategy = _owned_strategy(strategy_id, db, current_user)
    client = None
    if body.client_id is not None:
        client = _client(request, db, current_user, body.client_id)
    client_workspaces.assign_strategy(db, strategy, client)
    return {"strategy_id": str(strategy.id),
            "client_id": str(client.id) if client else None,
            "client_name": client.name if client else None}
