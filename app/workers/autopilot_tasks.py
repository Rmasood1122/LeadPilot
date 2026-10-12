"""Autopilot launch tasks (docs/features/autopilot-launch.md).

  leadpilot.autopilot.advance(strategy_id)   move one strategy's Autopilot on;
                                             enqueued when verification ends,
                                             when a person signs off failed
                                             passes, when Autopilot is turned
                                             on for a verified strategy, and at
                                             the end of its own sourcing chain.
  leadpilot.autopilot.sweep                  beat, every 15 minutes: every
                                             enabled row -- this is how a
                                             waiting channel resumes once its
                                             prerequisite (Gmail, LinkedIn,
                                             template, plan) appears.

QUEUE `default` (route leadpilot.autopilot.*): short database work. The
sourcing chain Autopilot starts is the ordinary five-stage lead chain, routed
exactly as the manual Find-leads chain, plus one `advance` link at the end.

NOTHING HERE SENDS. Enrolled messages go out through send_message_impl.
"""

from __future__ import annotations

import logging
import uuid

from celery import chain

from app.db.base import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)



def _uuid(value):
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


@celery_app.task(name="leadpilot.autopilot.advance")
def advance_strategy(strategy_id: str) -> str:
    from app.services import autopilot  # noqa: PLC0415

    session = SessionLocal()
    try:
        return autopilot.advance(session, _uuid(strategy_id))
    finally:
        session.close()


@celery_app.task(name="leadpilot.autopilot.sweep")
def sweep() -> dict:
    from app.services import autopilot  # noqa: PLC0415

    session = SessionLocal()
    try:
        return autopilot.sweep(session)
    finally:
        session.close()


@celery_app.task(name="leadpilot.autopilot.refresh_learning")
def refresh_learning() -> dict:
    """Beat, every 6 hours: the accounts' learned send-time rates into Redis
    (send_time.refresh_learning). The send path only ever reads them."""
    from app.services import send_time  # noqa: PLC0415

    session = SessionLocal()
    try:
        return send_time.refresh_learning(session)
    finally:
        session.close()


@celery_app.task(name="leadpilot.autopilot.reslot")
def reslot_strategy(strategy_id: str) -> int:
    """Move a strategy's scheduled messages into the person's new window
    (PUT /strategies/{id}/best-time answers 202 and enqueues this)."""
    from app.db.models import Strategy  # noqa: PLC0415
    from app.services import send_time  # noqa: PLC0415

    session = SessionLocal()
    try:
        strategy = session.get(Strategy, _uuid(strategy_id))
        return send_time.reslot(session, strategy) if strategy is not None else 0
    finally:
        session.close()


def enqueue_reslot(strategy_id) -> bool:
    """Tests monkeypatch this."""
    try:
        reslot_strategy.apply_async(args=[str(strategy_id)], retry=False)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not enqueue reslot for %s: %s", strategy_id, exc)
        return False


def enqueue_advance(session, strategy_id) -> bool:
    """Enqueue `advance` for a strategy whose Autopilot is ON. A strategy
    without it costs one indexed read and enqueues nothing. Never raises:
    the sweep picks up anything this misses. Tests monkeypatch this."""
    try:
        from app.services import autopilot  # noqa: PLC0415

        row = autopilot.row_for(session, _uuid(strategy_id))
        if row is None or not row.enabled:
            return False
        advance_strategy.apply_async(args=[str(strategy_id)], retry=False)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("autopilot: could not enqueue advance for %s: %s", strategy_id, exc)
        return False


def lead_chain(batch_id: str, strategy_id: str):
    """The existing five-stage lead chain -- routed exactly like the manual
    Find-leads chain (lead_tasks.start_lead_chain: no queue override, so the
    paid stages land on the leads queue) -- plus one `advance` link."""
    from app.workers import lead_tasks  # noqa: PLC0415

    return chain(
        lead_tasks.source_leads.s(batch_id),
        lead_tasks.enrich_leads.s(batch_id=batch_id),
        lead_tasks.find_missing_emails.s(batch_id=batch_id),
        lead_tasks.verify_emails.s(batch_id=batch_id),
        lead_tasks.finalize_lead_batch.s(batch_id=batch_id),
        # .si: immutable -- advance takes the strategy id, not finalize's summary.
        advance_strategy.si(strategy_id),
    )


def start_lead_chain(batch_id: str, strategy_id: str):
    """Publish the chain. Tests monkeypatch this."""
    return lead_chain(batch_id, strategy_id).apply_async()
