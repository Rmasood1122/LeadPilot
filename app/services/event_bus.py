"""The notification hub: one call fans an event out to push, Slack and webhooks.

WHY ONE HUB
Before the feature expansion there were five notify_* helpers in
app/services/notifications.py, each hand-wired to FCM only. The expansion adds
roughly a dozen new events and two new destinations (Slack, signed outbound
webhooks). Wiring each event to each destination at its call site is thirty-six
places to forget one, and this codebase's recurring failure mode is exactly
that: a second, slightly different implementation of the same concern that
silently drifts. So every NEW event goes through `emit`, and `emit` decides
where it goes.

DELIVERY GUARANTEES
Best effort, and never raising. Each destination is attempted independently --
a Slack outage does not stop the push, a missing Firebase config does not stop
the webhook -- and the caller gets back a dict of what happened, which the
tests assert on. A notification must never break the business operation that
produced it; that contract is inherited from notifications.dispatch.

DEEP LINKS
`deep_link` is an in-app PATH (e.g. "/leads/detail?id=..&tab=prep"). The push
payload carries it in the 3-slash custom-scheme form the Capacitor app routes
(see notifications._custom_link), and Slack gets an https link to the web app
built from FRONTEND_URL, so the same event opens the same screen on both.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings

logger = logging.getLogger(__name__)

# Every event the hub knows. A typo'd event name at a call site is a KeyError
# in the test suite rather than a notification that silently never matches a
# user's webhook subscription.
EVENTS: dict[str, str] = {
    "meeting_booked": "A meeting was booked",
    "meeting_prep_ready": "Meeting prep brief ready",
    "meeting_reminder_24h": "Meeting tomorrow",
    "meeting_reminder_1h": "Meeting in one hour",
    "reply_received": "A lead replied",
    "reply_interested": "High-intent reply",
    "lead_sourced": "Leads sourced",
    "campaign_paused": "Campaign paused",
    "strategy_mutated": "Strategy mutated",
    "approval_requested": "Campaign awaiting approval",
    "approval_decided": "Campaign approval decision",
    "objection_spike": "Objection rate spike",
    "domain_blacklisted": "Sending domain blacklisted",
    "deliverability_warning": "Email health warning",
    "call_completed": "AI call completed",
    "deal_won": "Deal closed-won",
    "loom_requested": "Personal video suggested",
}


def web_link(path: str) -> str:
    base = (settings.frontend_url or "").rstrip("/")
    clean = path if path.startswith("/") else f"/{path}"
    return f"{base}{clean}"


def emit(
    db: Session,
    user_id: uuid.UUID | str | None,
    event: str,
    *,
    title: str,
    body: str,
    deep_link: str | None = None,
    data: dict[str, Any] | None = None,
    slack_text: str | None = None,
    webhook_payload: dict | None = None,
    push: bool = True,
    slack: bool = True,
) -> dict[str, Any]:
    """Fan `event` out to every destination the user has. Never raises.

    `webhook_payload`, when given, is delivered to the user's outbound webhook
    targets subscribed to `event` (Zapier / Make). Events that make no sense
    to an external system (a reminder) simply pass None.
    """
    if event not in EVENTS:
        raise KeyError(f"unknown event {event!r} -- add it to event_bus.EVENTS")
    result: dict[str, Any] = {"event": event, "push": 0, "slack": False,
                              "webhooks": 0}
    if user_id is None:
        logger.warning("event %s has no recipient -- dropped", event)
        return result
    uid = user_id if isinstance(user_id, uuid.UUID) else uuid.UUID(str(user_id))

    if push:
        result["push"] = _push(uid, title, body, deep_link, event, data)
    if slack:
        result["slack"] = _slack(db, uid, title, slack_text or body, deep_link)
    if webhook_payload is not None:
        result["webhooks"] = _webhooks(db, uid, event, webhook_payload)
    # Feature Group 4: an event about a lead or deal is pushed to the user's
    # CRM straight away (crm_sync.on_event; a no-op with no CRM connected).
    _crm(db, uid, event, data, webhook_payload)
    return result


def lead_payload(lead) -> dict:
    """The lead as external systems (webhooks, Zapier) see it. One shape for
    every event, so a Zap built on reply_received also works on
    meeting_booked."""
    status = getattr(lead.status, "value", lead.status)
    return {
        "lead_id": str(lead.id),
        "strategy_id": str(lead.strategy_id) if lead.strategy_id else None,
        "full_name": lead.full_name, "email": lead.email, "company": lead.company,
        "title": lead.title, "phone": lead.phone,
        "linkedin_url": getattr(lead, "linkedin_url", None), "status": status,
    }


def _crm(db: Session, user_id: uuid.UUID, event: str, data: dict | None,
         payload: dict | None) -> int:
    try:
        from app.services import crm_sync  # noqa: PLC0415

        return crm_sync.on_event(db, user_id, event, data, payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("crm hook for %s/%s failed: %s", user_id, event, exc)
        return 0


def _push(user_id: uuid.UUID, title: str, body: str, deep_link: str | None,
          event: str, data: dict | None) -> int:
    from app.services import notifications  # noqa: PLC0415

    payload = {"event": event, **{k: str(v) for k, v in (data or {}).items()}}
    if deep_link:
        payload["deepLink"] = notifications._custom_link(deep_link)
    sent = {"n": 0}

    async def _go():
        sent["n"] = await notifications.send_to_user(
            user_id=user_id, title=title[:120], body=body[:900], data=payload,
        )

    # dispatch() handles both sync and running-loop callers and never raises.
    notifications.dispatch(_go())
    return sent["n"]


def _slack(db: Session, user_id: uuid.UUID, title: str, text: str,
           deep_link: str | None) -> bool:
    try:
        from app.integrations import slack  # noqa: PLC0415

        link = web_link(deep_link) if deep_link else None
        return slack.post_for_user(
            db, user_id, f"{title}\n{text}",
            blocks=slack.markdown_blocks(title, text, link),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("slack fan-out for %s failed: %s", user_id, exc)
        return False


def _webhooks(db: Session, user_id: uuid.UUID, event: str, payload: dict) -> int:
    try:
        from app.services import webhook_delivery  # noqa: PLC0415

        return len(webhook_delivery.fire_event(db, user_id, event, payload))
    except Exception as exc:  # noqa: BLE001
        logger.warning("webhook fan-out for %s/%s failed: %s", user_id, event, exc)
        return 0
