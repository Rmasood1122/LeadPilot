"""Workspaces API (Feature Group 8).

    GET    /workspaces                                   every workspace I am in
    GET    /workspaces/current                           the selected one + my role
    PATCH  /workspaces/current                           {name?, approval_required?} (owner)
    GET    /workspaces/current/members
    PATCH  /workspaces/current/members/{user_id}         {role}
    DELETE /workspaces/current/members/{user_id}         remove (or leave) -> 204
    GET    /workspaces/current/invitations               (manager+)
    POST   /workspaces/current/invitations               {email, role} -> 201
    DELETE /workspaces/current/invitations/{id}          -> 204
    POST   /workspaces/invitations/accept                {token}
    GET    /workspaces/current/branding
    PUT    /workspaces/current/branding                  (owner)
    POST   /workspaces/current/branding/logo             (owner, PNG/JPEG/WebP <= 1 MB)
    POST   /workspaces/current/domain/verify             (owner)
    GET    /branding?host=                               public: what a host shows

"current" is the workspace named by the X-Workspace-Id header, or the
caller's own. These routes are PERSONAL in rbac terms -- they always act as
the signed-in user -- and check the caller's role themselves.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.config import settings
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import User
from app.services import workspaces

router = APIRouter(tags=["workspaces"])

_LOGO_TYPES = {"image/png": ("png", b"\x89PNG"), "image/jpeg": ("jpg", b"\xff\xd8"),
               "image/webp": ("webp", b"RIFF")}
_LOGO_MAX_BYTES = 1_000_000


def _ctx(request: Request, db: Session, user: User) -> workspaces.Context:
    return workspaces.context_for_request(request, db, user)


def _workspace_out(ctx: workspaces.Context) -> dict:
    ws = ctx.workspace
    return {"id": str(ws.id), "name": ws.name, "slug": ws.slug, "role": ctx.role,
            "is_personal": ws.owner_user_id == ctx.actor.id,
            "approval_required": bool(ws.approval_required),
            "branding": workspaces.branding_out(ws)}


@router.get("/workspaces")
def my_workspaces(db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> list[dict]:
    return workspaces.memberships(db, current_user)


@router.get("/workspaces/current")
def current_workspace(request: Request, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    return _workspace_out(_ctx(request, db, current_user))


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    approval_required: bool | None = None


@router.patch("/workspaces/current")
def update_workspace(body: WorkspacePatch, request: Request, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> dict:
    ctx = _ctx(request, db, current_user)
    workspaces.update_branding(db, ctx, body.model_dump(exclude_unset=True, exclude_none=True))
    return _workspace_out(ctx)


@router.get("/workspaces/current/members")
def list_members(request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> list[dict]:
    return workspaces.members(db, _ctx(request, db, current_user).workspace)


class RoleIn(BaseModel):
    role: str


@router.patch("/workspaces/current/members/{user_id}")
def change_role(user_id: uuid.UUID, body: RoleIn, request: Request,
                db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)) -> list[dict]:
    ctx = _ctx(request, db, current_user)
    workspaces.set_role(db, ctx, user_id, body.role)
    return workspaces.members(db, ctx.workspace)


@router.delete("/workspaces/current/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> Response:
    workspaces.remove_member(db, _ctx(request, db, current_user), user_id)
    return Response(status_code=204)


@router.get("/workspaces/current/invitations")
def list_invitations(request: Request, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)) -> list[dict]:
    ctx = _ctx(request, db, current_user)
    if ctx.role not in ("owner", "manager"):
        raise HTTPException(status_code=403, detail="Invitations need a manager or above.")
    return workspaces.invitations(db, ctx.workspace)


class InviteIn(BaseModel):
    email: str = Field(max_length=320)
    role: str = "sdr"


@router.post("/workspaces/current/invitations", status_code=201)
def create_invitation(body: InviteIn, request: Request, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "workspace_invite", "RATE_LIMIT_AI_ACTION")
    invitation, token = workspaces.invite(db, _ctx(request, db, current_user), body.email,
                                          body.role)
    # The link is returned to the inviter as well as emailed, so it can be
    # shared another way; accepting still requires the invitee's own login
    # with the invited address.
    return {"id": str(invitation.id), "email": invitation.email, "role": invitation.role,
            "expires_at": invitation.expires_at.isoformat(),
            "link": workspaces.invite_link(token)}


@router.delete("/workspaces/current/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: uuid.UUID, request: Request,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> Response:
    workspaces.revoke_invitation(db, _ctx(request, db, current_user), invitation_id)
    return Response(status_code=204)


class AcceptIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/workspaces/invitations/accept")
def accept_invitation(body: AcceptIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "workspace_accept", "RATE_LIMIT_AI_ACTION")
    return workspaces.accept(db, current_user, body.token)


# --------------------------------------------------------------------------
# White label
# --------------------------------------------------------------------------


@router.get("/workspaces/current/branding")
def get_branding(request: Request, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)) -> dict:
    return workspaces.branding_out(_ctx(request, db, current_user).workspace, private=True)


class BrandingIn(BaseModel):
    white_label_enabled: bool | None = None
    brand_name: str | None = Field(default=None, max_length=100)
    primary_color: str | None = Field(default=None, max_length=7)
    support_email: str | None = Field(default=None, max_length=320)
    custom_domain: str | None = Field(default=None, max_length=253)


@router.put("/workspaces/current/branding")
def update_branding(body: BrandingIn, request: Request, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> dict:
    ctx = _ctx(request, db, current_user)
    ws = workspaces.update_branding(db, ctx, body.model_dump(exclude_unset=True))
    return workspaces.branding_out(ws, private=True)


@router.post("/workspaces/current/branding/logo", status_code=201)
async def upload_logo(request: Request, file: UploadFile = File(...),
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> dict:
    ctx = _ctx(request, db, current_user)
    if ctx.role != "owner":
        raise HTTPException(status_code=403, detail="Changing branding needs the owner.")
    kind = _LOGO_TYPES.get(file.content_type or "")
    if kind is None:
        raise HTTPException(status_code=415, detail="logo must be PNG, JPEG or WebP")
    data = await file.read(_LOGO_MAX_BYTES + 1)
    if len(data) > _LOGO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="logo must be 1 MB or smaller")
    ext, magic = kind
    # The declared type is the client's claim; the bytes are the truth. (SVG
    # is refused outright: it is script, served from the API's origin.)
    if not data.startswith(magic) or (ext == "webp" and data[8:12] != b"WEBP"):
        raise HTTPException(status_code=415, detail="the file is not the image type it claims")
    folder = Path(settings.media_dir) / "branding"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{ctx.workspace.id.hex}-{uuid.uuid4().hex[:8]}.{ext}"
    (folder / name).write_bytes(data)
    ctx.workspace.logo_url = f"{settings.public_base_url.rstrip('/')}/media/branding/{name}"
    db.commit()
    return workspaces.branding_out(ctx.workspace, private=True)


@router.post("/workspaces/current/domain/verify")
def verify_domain(request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)) -> dict:
    enforce_rate_limit(str(current_user.id), "domain_verify", "RATE_LIMIT_AI_ACTION")
    ctx = _ctx(request, db, current_user)
    verified = workspaces.verify_domain(db, ctx)
    return {"verified": verified, **workspaces.branding_out(ctx.workspace, private=True)}


@router.get("/branding")
def public_branding(host: str | None = None, db: Session = Depends(get_db)) -> dict:
    """No auth: the login page of a white-labelled domain needs its brand
    before anyone has signed in. Returns only what the page shows anyway."""
    return workspaces.branding_for_host(db, host)
