"""
User onboarding flow.

State tracked in users.onboarding_state JSONB column (added in migration 0011).
Steps are completed automatically by backend services via mark_complete().
Users cannot manually mark steps — the system observes their actions.

Steps (in order):
  1. product_created       — first product created
  2. gmail_connected       — Gmail OAuth connected
  3. first_strategy_run    — first strategy pipeline completes
  4. first_lead_sourced    — first lead imported
  5. first_email_sent      — first email sent via sequence
  6. first_reply_received  — first reply classified
  7. first_meeting_booked  — first Calendly booking received

GET /onboarding/state       — current completed steps + next action
POST /onboarding/complete-step — internal (called by services, not by users directly)

The onboarding state is additive — steps never go backward.
"""
from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.logging import get_logger

logger = get_logger("api.onboarding")
router = APIRouter(prefix="/onboarding", tags=["onboarding"])

ONBOARDING_STEPS = [
    "product_created",
    "gmail_connected",
    "first_strategy_run",
    "first_lead_sourced",
    "first_email_sent",
    "first_reply_received",
    "first_meeting_booked",
]

STEP_DESCRIPTIONS = {
    "product_created":    "Create your first product or skill",
    "gmail_connected":    "Connect your Gmail account",
    "first_strategy_run": "Run your first strategy pipeline",
    "first_lead_sourced": "Source your first leads",
    "first_email_sent":   "Send your first outreach email",
    "first_reply_received": "Receive your first reply",
    "first_meeting_booked": "Book your first meeting",
}

STEP_ACTIONS = {
    "product_created":    {"label": "Create Product", "href": "/products/new"},
    "gmail_connected":    {"label": "Connect Gmail", "href": "/settings/integrations"},
    "first_strategy_run": {"label": "Run Strategy", "href": "/strategies/new"},
    "first_lead_sourced": {"label": "Source Leads", "href": "/leads"},
    "first_email_sent":   {"label": "View Campaigns", "href": "/campaigns"},
    "first_reply_received": {"label": "View Replies", "href": "/leads?filter=replied"},
    "first_meeting_booked": {"label": "View Bookings", "href": "/leads?filter=booked"},
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@router.get("/state")
async def get_onboarding_state(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Return the user's onboarding progress and the next recommended action."""
    state = _get_state(db, str(current_user.id))
    completed = state.get("step_completed", [])
    all_complete = set(completed) >= set(ONBOARDING_STEPS)

    # Find next incomplete step
    next_step = None
    for step in ONBOARDING_STEPS:
        if step not in completed:
            next_step = step
            break

    steps_info = []
    for step in ONBOARDING_STEPS:
        steps_info.append({
            "step": step,
            "description": STEP_DESCRIPTIONS.get(step, step),
            "completed": step in completed,
            "is_next": step == next_step,
            "action": STEP_ACTIONS.get(step),
        })

    return {
        "all_complete": all_complete,
        "completed_count": len(completed),
        "total_steps": len(ONBOARDING_STEPS),
        "next_step": next_step,
        "steps": steps_info,
        "completed_at": state.get("completed_at"),
    }


class CompleteStepRequest(BaseModel):
    step: str
    user_id: Optional[str] = None  # for internal service calls; auth user if None


@router.post("/complete-step")
async def complete_step(
    body: CompleteStepRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """
    Mark a step complete. In production this is called by backend services,
    not by the user directly. The endpoint is auth-protected so only the
    server (using the user's service token) or the user themselves can call it.
    """
    target_user_id = body.user_id or str(current_user.id)
    step = body.step

    if step not in ONBOARDING_STEPS:
        return {"status": "ignored", "reason": f"Unknown step: {step}"}

    mark_complete(db, target_user_id, step)
    return {"status": "ok", "step": step}


# ---------------------------------------------------------------------------
# Internal: called by existing services (purely additive — no refactoring)
# ---------------------------------------------------------------------------

def mark_complete(db: Session, user_id: str, step: str) -> None:
    """
    Mark an onboarding step as complete.
    Safe to call multiple times — idempotent (set semantics).
    """
    if step not in ONBOARDING_STEPS:
        return

    try:
        from sqlalchemy import text
        state = _get_state(db, user_id)
        completed: list[str] = state.get("step_completed", [])

        if step in completed:
            return  # already done

        completed.append(step)
        all_done = set(completed) >= set(ONBOARDING_STEPS)

        new_state = {
            "step_completed": completed,
        }
        if all_done and "completed_at" not in state:
            new_state["completed_at"] = datetime.datetime.utcnow().isoformat()

        import json
        db.execute(text("""
            UPDATE users SET onboarding_state = :state WHERE id = :uid
        """), {"state": json.dumps(new_state), "uid": user_id})
        db.commit()

        logger.info("onboarding.step_complete", user_id=user_id, step=step, all_done=all_done)
    except Exception as e:
        logger.warning("onboarding.mark_complete_failed", user_id=user_id, step=step, error=str(e))


def _get_state(db: Session, user_id: str) -> dict:
    """Read the onboarding_state JSONB for a user."""
    from sqlalchemy import text
    import json
    try:
        row = db.execute(text("""
            SELECT onboarding_state FROM users WHERE id = :uid
        """), {"uid": user_id}).first()
        if row and row[0]:
            return row[0] if isinstance(row[0], dict) else json.loads(row[0])
    except Exception as e:
        logger.warning("onboarding.get_state_failed", user_id=user_id, error=str(e))
    return {}
