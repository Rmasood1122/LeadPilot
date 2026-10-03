"""Releasing a webhook's idempotency claim when its handler fails (NEW-03).

Both webhook receivers record the event id in processed_webhooks and COMMIT
it before doing the work, so a retried delivery is recognised and skipped.
That is right when the work succeeded. When the work RAISED, the claim used to
stay: the provider got a 500 and retried, the retry was answered "duplicate",
and the event was never processed. For a WhatsApp STOP that is an opt-out
lost for good, with nothing in any log to say so.

`release` undoes the claim, so the provider's retry is processed.

WHAT THIS DOES NOT COVER. A process that is killed between the claim and the
handler finishing never reaches the release, and that event is still lost.
Closing that needs the claim to carry a state (processing / done), which is a
schema change.
"""

from __future__ import annotations

import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import ProcessedWebhook

logger = logging.getLogger(__name__)


def release(db: Session, provider: str, event_id: str) -> None:
    """Remove the claim for (provider, event_id). Never raises: it runs while
    another exception is already propagating, and must not replace it."""
    try:
        db.rollback()       # whatever the failed handler left half-done
        db.execute(delete(ProcessedWebhook).where(
            ProcessedWebhook.provider == provider,
            ProcessedWebhook.event_id == event_id))
        db.commit()
        logger.warning("%s webhook event %s failed; its claim was released so "
                       "the provider's retry will be processed", provider, event_id)
    except Exception:  # noqa: BLE001
        logger.exception("%s webhook event %s failed AND its claim could not be "
                         "released -- the retry will be skipped as a duplicate",
                         provider, event_id)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
