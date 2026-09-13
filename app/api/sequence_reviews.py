"""Pre-send adversarial review endpoints (Feature A7).

POST /sequences/{id}/review            run a fresh review of the current content
GET  /sequences/{id}/review            the latest review (is_current says whether
                                       it still matches the content)
POST /sequences/{id}/review/override   owner/manager only, reason required

Enrollment and approval (app/api/sequences.py) call the same gate, so a launch
can never skip it; these endpoints exist so a person can see and act on the
findings first.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.sequences import _owned_sequence
from app.db.base import get_db
from app.db.models import User
from app.services import adversarial_review

router = APIRouter(tags=["sequences"])


class OverrideIn(BaseModel):
    reason: str = Field(min_length=adversarial_review.MIN_OVERRIDE_REASON, max_length=2000)


@router.post("/sequences/{sequence_id}/review")
def run_review(sequence_id: uuid.UUID, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    sequence = _owned_sequence(db, sequence_id, current_user)
    review = adversarial_review.run_review(db, sequence, current_user.id)
    return adversarial_review.review_out(review, sequence)


@router.get("/sequences/{sequence_id}/review")
def get_review(sequence_id: uuid.UUID, db: Session = Depends(get_db),
               current_user: User = Depends(get_current_user)) -> dict:
    sequence = _owned_sequence(db, sequence_id, current_user)
    review = adversarial_review.latest(db, sequence)
    if review is None:
        raise HTTPException(status_code=404, detail="this sequence has not been reviewed yet")
    return adversarial_review.review_out(review, sequence)


@router.post("/sequences/{sequence_id}/review/override")
def override_review(sequence_id: uuid.UUID, body: OverrideIn, request: Request,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> dict:
    """An explicit, logged decision to launch despite blocking findings. Only
    the workspace owner or a manager; the override is tied to the content hash
    it was made on, so editing the copy afterwards brings the gate back."""
    if getattr(request.state, "workspace_role", "owner") not in ("owner", "manager"):
        raise HTTPException(status_code=403, detail="Overriding a review needs a manager.")
    sequence = _owned_sequence(db, sequence_id, current_user)
    review = adversarial_review.latest(db, sequence)
    if review is None or review.content_hash != adversarial_review.content_hash(sequence):
        raise HTTPException(status_code=409,
                            detail="The content changed since the last review — run a review first.")
    actor = getattr(request.state, "actor", None) or current_user
    try:
        adversarial_review.override(db, review, actor=actor, reason=body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return adversarial_review.review_out(review, sequence)
