"""Feature 2 background work: classify one inbound reply.

  process_inbound_reply(reply_id)   dispatched the moment an InboundReply row
                                    is committed, from every channel that
                                    creates one (email polling, the Unipile
                                    LinkedIn webhook, the WhatsApp webhook)

On the `outreach` queue, with every other reply-path task: this is the same
work as routing a reply, it just answers a different question about it.

IDEMPOTENT BY CONSTRUCTION. A reply that already carries `classified_at` is
skipped -- a duplicate webhook delivery, a Celery redelivery after a lost
worker, or a manual re-enqueue costs nothing and cannot overwrite a draft the
user may already be editing. `force=True` is the deliberate override.

WHY THIS IS A TASK AND NOT INLINE. Classifying a reply is two model calls in
the worst case. Running that inside the webhook handler would hold the request
open for seconds and make Unipile/Meta retry on timeout -- creating duplicate
replies to classify. The webhook stores the reply, routes it the way it always
did, and hands this off.
"""

import logging

from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models import InboundReply
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def process_inbound_reply_impl(session: Session, reply_id, force: bool = False) -> dict:
    """Classify one reply and persist the result.

    WHAT IT RETURNS. {"status": "classified"|"skipped"|"not_found"|"failed",
    "category": str|None}.

    WHAT IT NEVER RAISES. Anything reachable from a reply. classify_reply and
    apply both swallow their own failures; this adds the already-classified
    guard and turns a missing row into a status rather than an exception, so a
    retry of a deleted reply does not spin.
    """
    import uuid  # noqa: PLC0415

    from app.services import reply_intelligence  # noqa: PLC0415

    try:
        reply = session.get(InboundReply, uuid.UUID(str(reply_id)))
    except (ValueError, TypeError):
        logger.warning("reply intelligence: %r is not a reply id", reply_id)
        return {"status": "not_found", "category": None}
    if reply is None:
        return {"status": "not_found", "category": None}
    if reply.classified_at is not None and not force:
        return {"status": "skipped", "category": reply.reply_category}

    result = reply_intelligence.classify_reply(session, reply.id)
    if result.get("error"):
        return {"status": "failed", "category": None}
    reply_intelligence.apply(session, reply, result)
    return {"status": "classified", "category": reply.reply_category}


@celery_app.task(name="app.workers.reply_tasks.process_inbound_reply")
def process_inbound_reply(reply_id: str, force: bool = False) -> dict:
    """Celery entry point. Safe to retry; see the module docstring."""
    session = SessionLocal()
    try:
        return process_inbound_reply_impl(session, reply_id, force=force)
    finally:
        session.close()


def enqueue(reply_id) -> bool:
    """Publish process_inbound_reply for `reply_id`.

    WHAT IT RETURNS. True when the job was published, False when the broker
    refused it.

    WHAT IT NEVER RAISES. Anything. This is called from inside webhook
    handlers that have already committed the reply and already routed it; a
    broker that is down must not turn a successfully stored reply into a 500
    and a provider retry. The reply simply goes unclassified.
    """
    try:
        process_inbound_reply.apply_async(args=[str(reply_id)], retry=False)
        return True
    except Exception:  # noqa: BLE001 -- see the docstring
        logger.exception("reply intelligence: could not enqueue reply %s", reply_id)
        return False
