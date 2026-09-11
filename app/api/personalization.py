"""Feature Group 2 API — voice profile, per-lead personalization inputs, Loom.

  /me/style-profile                      the user's writing voice
  /leads/{id}/personalization            what the next email will be written from
  /leads/{id}/personalization/refresh    force-refetch posts + news
  /leads/{id}/linkedin-url               set the profile URL by hand
  /leads/{id}/loom/*                     the personal-video workflow
  /public/video                          UNAUTHENTICATED: the page a prospect
                                         opens from step 2's video CTA

The public endpoint is the only unauthenticated route this group adds. It is
behind a Fernet-encrypted token (unforgeable, not enumerable), limited per IP,
and returns only a first name, a company name and a Loom embed id -- never an
email, a lead id or anything about the sender's account.
"""

# NOTE: deliberately NO `from __future__ import annotations` (FastAPI).

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.leads import _owned_lead
from app.core.rate_limiting import client_ip, enforce_rate_limit
from app.db.base import get_db
from app.db.models import Lead, User
from app.services import loom_video, personalization_context, style_profile
from app.services.notifications import owner_of_lead

router = APIRouter(tags=["personalization"])

_AI_LIMIT = "RATE_LIMIT_AI_ACTION"


# ---------------------------------------------------------------------------
# Voice profile
# ---------------------------------------------------------------------------


class StyleProfileIn(BaseModel):
    samples: list[str] = Field(min_length=1, max_length=style_profile.MAX_SAMPLES)


class StyleProfileOut(BaseModel):
    profile: dict | None
    samples: list[str]
    updated_at: datetime | None


@router.get("/me/style-profile", response_model=StyleProfileOut)
def get_style_profile(current_user: User = Depends(get_current_user)) -> StyleProfileOut:
    return StyleProfileOut(profile=current_user.style_profile_json,
                           samples=current_user.style_samples_json or [],
                           updated_at=current_user.style_profile_updated_at)


@router.put("/me/style-profile", response_model=StyleProfileOut)
def put_style_profile(body: StyleProfileIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)) -> StyleProfileOut:
    enforce_rate_limit(str(current_user.id), "ai_action", _AI_LIMIT)
    try:
        profile = style_profile.extract(db, current_user, body.samples)
    except style_profile.InvalidSamples as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=502,
                            detail=f"the style analysis failed: {exc}") from exc
    return StyleProfileOut(profile=profile, samples=current_user.style_samples_json or [],
                           updated_at=current_user.style_profile_updated_at)


@router.delete("/me/style-profile", status_code=204)
def delete_style_profile(db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)) -> None:
    style_profile.clear(db, current_user)


# ---------------------------------------------------------------------------
# Per-lead inputs
# ---------------------------------------------------------------------------


class LeadPersonalizationOut(BaseModel):
    linkedin_url: str | None
    linkedin_posts: list | None
    linkedin_posts_fetched_at: datetime | None
    company_news: list | None
    company_news_fetched_at: datetime | None
    loom: dict
    loom_page_url: str | None


def _out(lead: Lead) -> LeadPersonalizationOut:
    return LeadPersonalizationOut(
        linkedin_url=personalization_context.linkedin_url_for(lead),
        linkedin_posts=lead.linkedin_posts_json,
        linkedin_posts_fetched_at=lead.linkedin_posts_fetched_at,
        company_news=lead.company_news_json,
        company_news_fetched_at=lead.company_news_fetched_at,
        loom=loom_video.state(lead),
        loom_page_url=loom_video.page_url(lead) if loom_video.is_recorded(lead) else None,
    )


class LinkedInUrlIn(BaseModel):
    linkedin_url: str | None = Field(default=None, max_length=500)

    @field_validator("linkedin_url")
    @classmethod
    def _profile_url(cls, value):
        if value is None or not value.strip():
            return None
        from app.integrations.linkedin_posts import public_identifier  # noqa: PLC0415

        if not public_identifier(value):
            raise ValueError("must be a linkedin.com/in/<profile> URL")
        return value.strip()


class LoomIn(BaseModel):
    share_url: str = Field(min_length=10, max_length=500)


@router.get("/leads/{lead_id}/personalization", response_model=LeadPersonalizationOut)
def get_lead_personalization(lead_id: uuid.UUID, db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    return _out(_owned_lead(db, lead_id, current_user))


@router.post("/leads/{lead_id}/personalization/refresh",
             response_model=LeadPersonalizationOut)
def refresh_lead_personalization(lead_id: uuid.UUID, db: Session = Depends(get_db),
                                 current_user: User = Depends(get_current_user)):
    enforce_rate_limit(str(current_user.id), "ai_action", _AI_LIMIT)
    lead = _owned_lead(db, lead_id, current_user)
    personalization_context.ensure_fresh(db, lead, owner_id=current_user.id, force=True)
    return _out(lead)


@router.put("/leads/{lead_id}/linkedin-url", response_model=LeadPersonalizationOut)
def set_linkedin_url(lead_id: uuid.UUID, body: LinkedInUrlIn,
                     db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    lead = _owned_lead(db, lead_id, current_user)
    if body.linkedin_url != lead.linkedin_url:
        lead.linkedin_url = body.linkedin_url
        # A different person's posts must not survive a URL correction.
        lead.linkedin_posts_json = None
        lead.linkedin_posts_fetched_at = None
        db.commit()
    return _out(lead)


@router.post("/leads/{lead_id}/loom/script", response_model=LeadPersonalizationOut)
def write_loom_script(lead_id: uuid.UUID, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    """Write (or rewrite) the recording script on demand, whatever the score."""
    enforce_rate_limit(str(current_user.id), "ai_action", _AI_LIMIT)
    lead = _owned_lead(db, lead_id, current_user)
    try:
        script = loom_video.write_script(lead)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"the script could not be written: {exc}") from exc
    current = loom_video.state(lead)
    status = current.get("status") if current.get("status") == "recorded" else "suggested"
    lead.loom_video_json = {**current, **script, "status": status}
    db.commit()
    return _out(lead)


@router.put("/leads/{lead_id}/loom", response_model=LeadPersonalizationOut)
def record_loom(lead_id: uuid.UUID, body: LoomIn, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    lead = _owned_lead(db, lead_id, current_user)
    try:
        loom_video.record(db, lead, body.share_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _out(lead)


@router.post("/leads/{lead_id}/loom/skip", response_model=LeadPersonalizationOut)
def skip_loom(lead_id: uuid.UUID, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    lead = _owned_lead(db, lead_id, current_user)
    loom_video.skip(db, lead)
    return _out(lead)


# ---------------------------------------------------------------------------
# Public video page
# ---------------------------------------------------------------------------


class PublicVideoOut(BaseModel):
    first_name: str
    company: str | None
    title: str | None
    embed_url: str


@router.get("/public/video", response_model=PublicVideoOut)
def public_video(request: Request, t: str = Query(min_length=20, max_length=2000),
                 db: Session = Depends(get_db)) -> PublicVideoOut:
    enforce_rate_limit(f"ip:{client_ip(request)}", "public_video",
                       "RATE_LIMIT_PUBLIC_VIDEO")
    try:
        lead_id = loom_video.parse_token(t)
    except Exception:  # noqa: BLE001 -- a bad token is simply "not found"
        raise HTTPException(status_code=404, detail="video not found") from None
    lead = db.get(Lead, lead_id)
    if lead is None or not loom_video.is_recorded(lead) or owner_of_lead(db, lead) is None:
        raise HTTPException(status_code=404, detail="video not found")
    state = loom_video.state(lead)
    first = (lead.full_name or "").split(" ")[0] or "there"
    return PublicVideoOut(first_name=first, company=lead.company,
                          title=state.get("title"),
                          embed_url=f"https://www.loom.com/embed/{state['embed_id']}")
