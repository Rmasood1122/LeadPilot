"""Reply kill switch (Feature 4): one contact, one account, or the platform.

Three independent levels, checked at SEND time on every outbound path:
  platform  -- admin setting `messaging_global_pause` (emergency, all accounts)
  account   -- users.messaging_paused_at   (the owner pressed "pause all")
  contact   -- leads.messaging_paused_at   (the owner paused one person)

A pause never deletes or cancels anything: scheduled messages stay SCHEDULED
and go out after a resume (subject to every other gate, which still applies).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

REASONS = ("manual", "spam", "bounce")


class PauseError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _check_reason(reason: str) -> str:
    if reason not in REASONS:
        raise PauseError(f"reason must be one of {', '.join(REASONS)}")
    return reason


def blocked_reason(db: Session, *, lead=None, user=None) -> str | None:
    """'platform_paused' | 'account_paused' | 'contact_paused' | None.

    Fails CLOSED on the platform switch only if it is readable; an unreadable
    settings row falls back to the default (not paused) like every setting."""
    from app.db.models import User  # noqa: PLC0415
    from app.services import system_settings  # noqa: PLC0415
    from app.services.notifications import owner_of_lead  # noqa: PLC0415

    if system_settings.get(db, "messaging_global_pause"):
        return "platform_paused"
    if user is None and lead is not None:
        owner_id = owner_of_lead(db, lead)
        user = db.get(User, owner_id) if owner_id is not None else None
    if user is not None and user.messaging_paused_at is not None:
        return "account_paused"
    if lead is not None and lead.messaging_paused_at is not None:
        return "contact_paused"
    return None


def pause_contact(db: Session, lead, *, reason: str = "manual") -> None:
    _check_reason(reason)
    if lead.messaging_paused_at is None:
        lead.messaging_paused_at = _now()
        lead.messaging_paused_reason = reason
    db.commit()


def resume_contact(db: Session, lead) -> None:
    lead.messaging_paused_at = None
    lead.messaging_paused_reason = None
    db.commit()


def pause_account(db: Session, user, *, reason: str = "manual") -> None:
    _check_reason(reason)
    if user.messaging_paused_at is None:
        user.messaging_paused_at = _now()
        user.messaging_paused_reason = reason
    db.commit()


def resume_account(db: Session, user) -> None:
    user.messaging_paused_at = None
    user.messaging_paused_reason = None
    db.commit()


def refusal_text(blocked: str) -> str:
    return {
        "platform_paused": "Messaging is paused platform-wide by the administrator.",
        "account_paused": "Your messaging is paused. Resume it to send.",
        "contact_paused": "Messaging to this contact is paused.",
    }[blocked]
