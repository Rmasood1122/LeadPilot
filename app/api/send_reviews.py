"""Human review queue for high-risk sends (Part 1, Feature 5).

GET  /send-reviews                 the queue, oldest first
GET  /send-reviews/count           the pending count (for the nav badge)
GET  /send-reviews/{id}            one held message, with its triggers
POST /send-reviews/{id}/approve    send it — optionally with an edit
POST /send-reviews/{id}/reject     never send it; a reason is required

These are new paths. `/sequences/{id}/review*` (Feature A7) reviews a
sequence's CONTENT before launch and is untouched; this reviews one MESSAGE at
send time, for reasons no pre-launch review could know.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limiting import enforce_rate_limit
from app.db.base import get_db
from app.db.models import SendReview, User
from app.services import send_review

router = APIRouter(tags=["send-reviews"])


class ApproveIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)
    #: A reviewer may fix the copy instead of rejecting it — the whole point of
    #: a human gate is that the human can improve the message, not only veto it.
    subject: str | None = Field(default=None, max_length=500)
    body: str | None = None


class RejectIn(BaseModel):
    #: Required, and long enough to be a reason rather than a shrug. A
    #: rejected message is never sent; the next person to read the queue needs
    #: to know why, and so does the campaign post-mortem.
    note: str = Field(min_length=5, max_length=500)


def _owned(db: Session, review_id: uuid.UUID, current_user: User) -> SendReview:
    """404 rather than 403 for another account's review, so its existence
    cannot be probed."""
    review = db.get(SendReview, review_id)
    if review is None or review.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="review not found")
    return review


@router.get("/send-reviews")
def list_send_reviews(
    status: str = Query(default=send_review.PENDING,
                        pattern="^(pending|approved|rejected|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Oldest first — a queue, not a feed. The message that has been waiting
    longest is the one most at risk of going stale."""
    return send_review.queue(db, current_user.id, status=status, limit=limit, offset=offset)


@router.get("/send-reviews/count")
def count_send_reviews(db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)) -> dict:
    """Cheap enough for the nav badge to poll."""
    return {"pending": send_review.pending_count(db, current_user.id)}


@router.get("/send-reviews/{review_id}")
def get_send_review(review_id: uuid.UUID, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)) -> dict:
    return send_review.review_out(db, _owned(db, review_id, current_user))


@router.post("/send-reviews/{review_id}/approve")
def approve_send_review(review_id: uuid.UUID, body: ApproveIn,
                        db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)) -> dict:
    """Approve and return the message to the send queue.

    An edit re-hashes the approved copy, so what the reviewer read and changed
    is exactly what the send path checks against before transmitting."""
    enforce_rate_limit(str(current_user.id), "send_review_decision", "RATE_LIMIT_CRM_WRITE")
    review = _owned(db, review_id, current_user)
    if review.status != send_review.PENDING:
        raise HTTPException(status_code=409,
                            detail=f"this review was already {review.status}")
    send_review.approve(db, review, actor_user_id=current_user.id, note=body.note,
                        subject=body.subject, body=body.body)
    return send_review.review_out(db, review)


@router.post("/send-reviews/{review_id}/reject")
def reject_send_review(review_id: uuid.UUID, body: RejectIn,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)) -> dict:
    """Never send this message.

    The message is cancelled; the enrollment keeps running. Rejecting one
    badly-timed email should not end the relationship."""
    enforce_rate_limit(str(current_user.id), "send_review_decision", "RATE_LIMIT_CRM_WRITE")
    review = _owned(db, review_id, current_user)
    if review.status != send_review.PENDING:
        raise HTTPException(status_code=409,
                            detail=f"this review was already {review.status}")
    send_review.reject(db, review, actor_user_id=current_user.id, note=body.note)
    return send_review.review_out(db, review)
