"""Identity & location verification at onboarding (Section B).

The account holder answers three questions -- where are YOU, are you signing
up as an individual or a company, and (for a company) where is the COMPANY --
and the declared personal country is compared with where the request actually
comes from (app/integrations/geolocation.py).

A MISMATCH IS A RISK SIGNAL, NOT A REJECTION. VPNs, corporate egress and
travel all produce honest mismatches, so a mismatch sets
`geo_review_status = "pending"` for the admin panel and writes an
account_security_events row; the user carries on. "unknown" (no public IP, the
provider was down, geolocation disabled) is recorded as unknown and is NOT
queued for review -- a review queue full of "we could not tell" teaches admins
to ignore it.

Also home of the PHONE GATE (`require_verified_phone`), because both facts
live on the same row and every gated caller already imports this module.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AccountSecurityEvent, User
from app.integrations import geolocation
from app.services.countries import normalize_country

ACCOUNT_TYPES = ("individual", "company")
GEO_MATCH, GEO_MISMATCH, GEO_UNKNOWN = "match", "mismatch", "unknown"
REVIEW_PENDING, REVIEW_CLEARED, REVIEW_CONFIRMED = "pending", "cleared", "confirmed_risk"
REVIEW_DECISIONS = (REVIEW_CLEARED, REVIEW_CONFIRMED)

# The 403 detail every phone-gated route returns. A CONTRACT, like
# auth.EMAIL_NOT_VERIFIED: the frontend matches on it to send the user to the
# verification screen instead of showing a generic error.
PHONE_NOT_VERIFIED = "PHONE_NOT_VERIFIED"


class IdentityError(ValueError):
    """A submitted identity answer is invalid. The message is user-facing."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def record_event(db: Session, *, event: str, user: User | None = None,
                 email: str | None = None, ip: str | None = None,
                 country: str | None = None, details: dict | None = None
                 ) -> AccountSecurityEvent:
    """Add (not commit) one audit row; it rides the caller's transaction."""
    row = AccountSecurityEvent(
        user_id=user.id if user is not None else None,
        email=(email or (user.email if user is not None else None) or None),
        event=event[:40], ip=(ip or None) and ip[:64],
        country=(country or None) and country[:2], details_json=details or None,
    )
    db.add(row)
    return row


def identity_complete(user: User) -> bool:
    if not normalize_country(user.personal_country):
        return False
    if user.account_type == "individual":
        return True
    return user.account_type == "company" and bool(normalize_country(user.company_country))


def phone_gate_applies(user: User) -> bool:
    return bool(settings.require_phone_verification
                and getattr(user, "identity_required", False)
                and not getattr(user, "phone_verified", False))


def status(user: User) -> dict:
    """What the onboarding verification screen renders and routes on."""
    complete = identity_complete(user)
    phone_ok = bool(user.phone_verified)
    next_step = None
    if not complete:
        next_step = "identity"
    elif not phone_ok:
        next_step = "phone"
    return {
        "identity_required": bool(user.identity_required),
        "identity_complete": complete,
        "phone_verified": phone_ok,
        "phone_required": bool(settings.require_phone_verification),
        "next_step": next_step,
        "personal_country": user.personal_country,
        "account_type": user.account_type,
        "company_name": user.company_name,
        "company_country": user.company_country,
        "phone_number_masked": _mask(user.phone_number),
        # The user is told a review MAY happen, never the detected country:
        # echoing "we think you are in X" back is a free VPN-tuning oracle.
        "under_review": user.geo_review_status == REVIEW_PENDING,
    }


def _mask(phone: str | None) -> str | None:
    from app.integrations.sms import mask_phone  # noqa: PLC0415

    return mask_phone(phone) if phone else None


def submit_identity(db: Session, user: User, *, personal_country: str,
                    account_type: str, company_name: str | None = None,
                    company_country: str | None = None, ip: str | None = None,
                    now: datetime | None = None) -> dict:
    """Validate and store the answers, then cross-check the location.

    Raises IdentityError on invalid input. Commits. Re-submitting is allowed
    (a typo'd country must be fixable); every submission re-runs the check,
    and a pending review is never silently cleared by a resubmission -- only
    an admin clears one.
    """
    now = now or _now()
    personal = normalize_country(personal_country)
    if personal is None:
        raise IdentityError("Choose the country you are located in.")
    kind = (account_type or "").strip().lower()
    if kind not in ACCOUNT_TYPES:
        raise IdentityError("Choose whether you are signing up as an individual or a company.")
    company = None
    company_label = None
    if kind == "company":
        company = normalize_country(company_country)
        if company is None:
            raise IdentityError("Choose the country your company is registered or operates in.")
        company_label = (company_name or "").strip()[:200] or None

    user.personal_country = personal
    user.account_type = kind
    user.company_country = company
    user.company_name = company_label
    user.identity_submitted_at = now

    detected = geolocation.lookup_country(ip)
    check = GEO_UNKNOWN if detected is None else (GEO_MATCH if detected == personal
                                                  else GEO_MISMATCH)
    user.geo_detected_country = detected
    user.geo_check_status = check
    if check == GEO_MISMATCH and user.geo_review_status != REVIEW_CONFIRMED:
        user.geo_review_status = REVIEW_PENDING
        user.geo_reviewed_at = None
        user.geo_reviewed_by = None
        user.geo_review_note = None
    record_event(
        db, event="geo_mismatch" if check == GEO_MISMATCH else "identity_submitted",
        user=user, ip=ip, country=detected,
        details={"declared_country": personal, "detected_country": detected,
                 "geo_check": check, "account_type": kind, "company_country": company},
    )
    db.commit()
    return status(user)


def require_verified_phone(user: User) -> None:
    """403 PHONE_NOT_VERIFIED for a post-0039 account without a proved number.

    Gated (see BUILD_DECISIONS.md): starting outreach (enroll / approve a
    sequence), buying a plan, and minting a public share link -- the three
    actions where an anonymous throwaway account costs someone else money or
    reputation. Browsing, research and CRM work are NOT gated.
    """
    if phone_gate_applies(user):
        raise HTTPException(status_code=403, detail=PHONE_NOT_VERIFIED)


def review(db: Session, user: User, *, decision: str, reviewer_email: str,
           note: str | None = None, now: datetime | None = None) -> None:
    if decision not in REVIEW_DECISIONS:
        raise IdentityError(f"decision must be one of {', '.join(REVIEW_DECISIONS)}")
    user.geo_review_status = decision
    user.geo_reviewed_by = reviewer_email[:320]
    user.geo_reviewed_at = now or _now()
    user.geo_review_note = (note or "").strip()[:500] or None
    record_event(db, event=f"geo_review_{decision}", user=user,
                 details={"reviewer": reviewer_email, "note": user.geo_review_note})
    db.commit()


def review_out(user: User) -> dict:
    return {
        "user_id": str(user.id), "email": user.email,
        "personal_country": user.personal_country,
        "geo_detected_country": user.geo_detected_country,
        "geo_check_status": user.geo_check_status,
        "geo_review_status": user.geo_review_status,
        "account_type": user.account_type, "company_name": user.company_name,
        "company_country": user.company_country, "signup_ip": user.signup_ip,
        "phone_verified": bool(user.phone_verified),
        "identity_submitted_at": user.identity_submitted_at.isoformat()
        if user.identity_submitted_at else None,
        "geo_reviewed_by": user.geo_reviewed_by,
        "geo_reviewed_at": user.geo_reviewed_at.isoformat() if user.geo_reviewed_at else None,
        "geo_review_note": user.geo_review_note,
    }
