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


# ---------------------------------------------------------------------------
# Identity, location and phone verification (Sections B + C, migration 0039)
# ---------------------------------------------------------------------------
#
# Sync `def` handlers (unlike the async ones above): they do blocking DB and
# HTTP work (geolocation, SMS), which FastAPI runs on its threadpool for a sync
# handler instead of stalling the event loop.
#
# Rate limits are enforced INSIDE the handlers, after body validation, per the
# Finding 3 ordering rule in app/core/rate_limiting.py::enforce_rate_limit.

from fastapi import HTTPException, Request  # noqa: E402
from pydantic import Field  # noqa: E402

from app.core.rate_limiting import client_ip, enforce_rate_limit  # noqa: E402
from app.services import identity as identity_svc  # noqa: E402
from app.services import phone_verification as phone_svc  # noqa: E402
from app.services.countries import country_list  # noqa: E402

OTP_SEND_WINDOW_SECONDS = 3600
OTP_VERIFY_WINDOW_SECONDS = 900


class IdentityIn(BaseModel):
    personal_country: str = Field(min_length=2, max_length=2)
    account_type: str = Field(pattern="^(individual|company)$")
    company_name: Optional[str] = Field(default=None, max_length=200)
    company_country: Optional[str] = Field(default=None, min_length=2, max_length=2)


class PhoneSendIn(BaseModel):
    phone_number: str = Field(min_length=8, max_length=32)


class PhoneVerifyIn(BaseModel):
    code: str = Field(min_length=4, max_length=12)


@router.get("/countries")
def list_countries() -> dict:
    """Public: the ISO country list the verification form offers."""
    return {"countries": country_list()}


@router.get("/verification")
def verification_status(current_user=Depends(get_current_user)) -> dict:
    return identity_svc.status(current_user)


@router.put("/identity")
def submit_identity(
    body: IdentityIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Store where the person is, individual vs company, and the company's
    country; cross-check the personal country against the request's IP.

    A mismatch never fails this request -- it queues an admin review."""
    try:
        return identity_svc.submit_identity(
            db, current_user, personal_country=body.personal_country,
            account_type=body.account_type, company_name=body.company_name,
            company_country=body.company_country, ip=client_ip(request))
    except identity_svc.IdentityError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _phone_error(exc: "phone_svc.PhoneVerificationError") -> HTTPException:
    headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after else None
    return HTTPException(status_code=exc.status_code, detail=str(exc), headers=headers)


@router.post("/phone/send")
def send_phone_code(
    body: PhoneSendIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    if current_user.phone_verified:
        raise HTTPException(status_code=409, detail="Your phone number is already verified.")
    try:
        phone = phone_svc.normalize_phone(body.phone_number)
    except phone_svc.PhoneVerificationError as exc:
        raise _phone_error(exc)
    # Two keys, like /auth/login: per account stops one user cycling numbers,
    # per number stops many accounts pumping one (possibly premium) number.
    enforce_rate_limit(f"user:{current_user.id}", "otp_send", "RATE_LIMIT_OTP_SEND",
                       OTP_SEND_WINDOW_SECONDS)
    enforce_rate_limit(f"phone:{phone}", "otp_send_phone", "RATE_LIMIT_OTP_SEND",
                       OTP_SEND_WINDOW_SECONDS)
    try:
        result = phone_svc.send_code(db, current_user, phone)
    except phone_svc.PhoneVerificationError as exc:
        raise _phone_error(exc)
    from app.integrations.sms import mask_phone  # noqa: PLC0415

    return {"status": "sent", "phone_number_masked": mask_phone(result.phone_number),
            "expires_at": result.expires_at.isoformat(),
            "resend_available_at": result.resend_available_at.isoformat()}


@router.post("/phone/verify")
def verify_phone_code(
    body: PhoneVerifyIn,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    enforce_rate_limit(f"user:{current_user.id}", "otp_verify", "RATE_LIMIT_OTP_VERIFY",
                       OTP_VERIFY_WINDOW_SECONDS)
    try:
        outcome, remaining = phone_svc.verify_code(db, current_user, body.code)
    except phone_svc.PhoneVerificationError as exc:
        raise _phone_error(exc)
    if outcome == phone_svc.VERIFIED:
        return {"status": "verified", **identity_svc.status(current_user)}
    messages = {
        phone_svc.INVALID: "That code is not right. Check the text and try again.",
        phone_svc.EXPIRED: "That code has expired. Ask for a new one.",
        phone_svc.LOCKED: "Too many wrong attempts. Ask for a new code.",
        phone_svc.NO_CODE: "Ask for a code first.",
    }
    raise HTTPException(status_code=400, detail=messages[outcome],
                        headers={"X-Attempts-Remaining": str(remaining)}
                        if remaining is not None else None)
