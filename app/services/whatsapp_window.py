"""The WhatsApp 24-hour customer-service window — Milestone 4, Chunk 3.

Model (Meta policy; # TODO: verify current Meta policy details):
  - the window for a lead is OPEN for exactly 24 hours from the timestamp
    of their most recent INBOUND message (persisted by the webhook since
    Chunk 1 as Lead.whatsapp_last_inbound_at);
  - every new inbound message resets the 24 hours;
  - no inbound message ever => the window has never been open;
  - business-initiated sends (templates) do NOT open the window — only
    the prospect can open it, by messaging first.

`window_state()` is COMPUTED from the stored timestamp on every call —
never cached as a boolean — so it cannot go stale between scheduling and
sending. Every function takes an explicit `now` for deterministic tests.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import Lead

WINDOW_HOURS = 24  # TODO: verify current Meta policy details


@dataclass(frozen=True)
class WindowState:
    open: bool
    expires_at: datetime | None  # None <=> never opened / long closed

    @property
    def closed(self) -> bool:
        return not self.open


CLOSED = WindowState(open=False, expires_at=None)


def window_state_for_lead(lead: Lead | None,
                          now: datetime | None = None) -> WindowState:
    now = now or datetime.now(timezone.utc)
    if lead is None or lead.whatsapp_last_inbound_at is None:
        return CLOSED
    last = lead.whatsapp_last_inbound_at
    if last.tzinfo is None:  # SQLite drops tzinfo; stored values are UTC
        last = last.replace(tzinfo=timezone.utc)
    expires_at = last + timedelta(hours=WINDOW_HOURS)
    if now < expires_at:
        return WindowState(open=True, expires_at=expires_at)
    return WindowState(open=False, expires_at=expires_at)


def window_state(session: Session, lead_id: uuid.UUID,
                 now: datetime | None = None) -> WindowState:
    """OPEN(expires_at) | CLOSED for this lead, computed live."""
    return window_state_for_lead(session.get(Lead, lead_id), now)
