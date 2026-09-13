"""Shareable ROI dashboard links (Feature A6).

POST   /share-links                create; the token is returned ONCE
GET    /share-links                the account's links with status and views
DELETE /share-links/{id}           revoke (immediate; the row is kept as a record)
GET    /public/roi/{token}         PUBLIC, read-only dashboard payload

The account is the workspace: in a workspace, get_current_user resolves the
owner, so a manager's link shows the workspace's numbers. Creating a link is
phone-gated (PHONE_NOT_VERIFIED) -- see BUILD_DECISIONS.md C1.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import client_ip, enforce_rate_limit
from app.db.base import get_db
from app.db.models import ShareLink, User
from app.services import identity as identity_svc
from app.services import share_links

router = APIRouter(tags=["share-links"])

_PUBLIC_HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
                   "Referrer-Policy": "no-referrer"}
_NOT_FOUND = "This dashboard link is invalid, has expired or was revoked."


class ShareLinkIn(BaseModel):
    label: str = Field(default="ROI dashboard", max_length=120)
    strategy_id: uuid.UUID | None = None
    expires_in_days: int = Field(default=30, ge=1, le=share_links.MAX_EXPIRY_DAYS)


def _raise(exc: share_links.ShareLinkError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/share-links", status_code=201)
def create_link(body: ShareLinkIn, request: Request, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    identity_svc.require_verified_phone(current_user)
    actor = getattr(request.state, "actor", None) or current_user
    try:
        link, token = share_links.create(db, owner=current_user, actor=actor, label=body.label,
                                         strategy_id=body.strategy_id,
                                         expires_in_days=body.expires_in_days)
    except share_links.ShareLinkError as exc:
        raise _raise(exc)
    return {**share_links.link_out(link), "token": token, "url": share_links.share_url(token)}


@router.get("/share-links")
def list_links(db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> list[dict]:
    rows = db.execute(select(ShareLink).where(ShareLink.user_id == current_user.id)
                      .order_by(ShareLink.created_at.desc())).scalars()
    return [share_links.link_out(r) for r in rows]


@router.delete("/share-links/{link_id}")
def revoke_link(link_id: uuid.UUID, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> dict:
    try:
        link = share_links.get_owned(db, link_id, current_user.id)
    except share_links.ShareLinkError as exc:
        raise _raise(exc)
    return share_links.link_out(share_links.revoke(db, link))


@router.get("/public/roi/{token}")
def public_roi(token: str, request: Request, db: Session = Depends(get_db)) -> JSONResponse:
    """Unauthenticated by design. Rate limited per IP BEFORE the lookup so the
    endpoint cannot be used to enumerate tokens; unknown, expired and revoked
    all answer the same 404."""
    enforce_rate_limit(f"ip:{client_ip(request)}", "public_roi", "RATE_LIMIT_PUBLIC_SHARE")
    link = share_links.resolve(db, token)
    if link is None:
        return JSONResponse(status_code=404, content={"detail": _NOT_FOUND},
                            headers=_PUBLIC_HEADERS)
    return JSONResponse(content=share_links.public_dashboard(db, link), headers=_PUBLIC_HEADERS)
