"""Feature Group 6: transcript analysis, off the webhook's request path.

A provider's end-of-call webhook must be acknowledged quickly or it retries;
a Claude analysis of a ten-minute transcript is not quick. So the webhook
stores the raw result and enqueues this. It runs on the `outreach` queue --
it is the phone channel's equivalent of reply routing, and routes the lead
the same way a reply does.
"""

from __future__ import annotations

import logging
import uuid

from app.db.base import SessionLocal
from app.db.models import Call
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.call_tasks.analyze_call", bind=True, max_retries=2)
def analyze_call(self, call_id: str) -> str:
    from app.services import phone_calls  # noqa: PLC0415

    session = SessionLocal()
    try:
        call = session.get(Call, uuid.UUID(call_id))
        if call is None:
            return "missing"
        from app.services import usage_meter  # noqa: PLC0415

        with usage_meter.scope(session, strategy_id=call.strategy_id, user_id=call.user_id,
                               purpose="call_analysis"):
            return phone_calls.analyze(session, call)["outcome"]
    except Exception as exc:
        session.rollback()
        logger.exception("call analysis failed for %s -- retrying", call_id)
        raise self.retry(exc=exc, countdown=60)
    finally:
        session.close()


def enqueue_analysis(call_id) -> bool:
    """Never raises; tests monkeypatch this."""
    try:
        analyze_call.apply_async(args=[str(call_id)], retry=False)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not queue call analysis %s: %s", call_id, exc)
        return False
