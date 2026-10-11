"""F06 Quickstart background work.

  start(run_id)  fetch the website, derive the ICP, create the lead batch, then
                 publish the EXISTING lead chain (lead_tasks: source -> enrich
                 -> find emails -> verify -> finalize) with one extra link,
                 `draft`, at its end.
  draft(run_id)  write the review-only drafts for the batch's VERIFIED leads.

QUEUE. Both tasks are routed to `default`, and the lead chain of a Quickstart
run is published to `default` too (an explicit per-signature override; the
same tasks keep their normal `pipeline` route everywhere else). The Quickstart
request enqueues the strategy's full research pipeline on `pipeline` in the
same moment, and that queue runs at concurrency 2: sourcing behind a
144-step pipeline would turn a minutes-long first result into an hours-long
one, which is the whole problem this feature answers.

NOTHING HERE SENDS. See app/services/quickstart.py.
"""

from __future__ import annotations

import logging
import uuid

from celery import chain

from app.db.base import SessionLocal
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

QUEUE = "default"


def lead_chain(batch_id: str, run_id: str):
    """The existing five-stage lead chain + the draft step, on QUEUE."""
    from app.workers import lead_tasks  # noqa: PLC0415

    return chain(
        lead_tasks.source_leads.s(batch_id).set(queue=QUEUE),
        lead_tasks.enrich_leads.s(batch_id=batch_id).set(queue=QUEUE),
        lead_tasks.find_missing_emails.s(batch_id=batch_id).set(queue=QUEUE),
        lead_tasks.verify_emails.s(batch_id=batch_id).set(queue=QUEUE),
        lead_tasks.finalize_lead_batch.s(batch_id=batch_id).set(queue=QUEUE),
        # .si: immutable -- the draft step takes the run id, not finalize's summary.
        draft_quickstart.si(run_id).set(queue=QUEUE),
    )


def start_lead_chain(batch_id: str, run_id: str):
    """Publish the chain. Tests monkeypatch this."""
    return lead_chain(batch_id, run_id).apply_async()


def _give_up(session, run_id: str, exc: Exception) -> None:
    """Last retry failed: say so on the run instead of leaving it 'in progress'
    forever. Never raises."""
    from app.db.models import QuickstartRun  # noqa: PLC0415
    from app.services import quickstart  # noqa: PLC0415

    try:
        session.rollback()
        run = session.get(QuickstartRun, uuid.UUID(run_id))
        if run is not None and run.status in quickstart.IN_PROGRESS:
            run.status = quickstart.FAILED
            run.error = f"stopped after retries: {type(exc).__name__}"[:500]
            session.commit()
    except Exception:  # noqa: BLE001
        logger.exception("could not mark quickstart run %s failed", run_id)


@celery_app.task(name="leadpilot.quickstart.start", bind=True, max_retries=2)
def start_quickstart(self, run_id: str):
    from app.services import quickstart  # noqa: PLC0415

    session = SessionLocal()
    try:
        batch_id = quickstart.start_impl(session, uuid.UUID(run_id))
    except Exception as exc:
        session.rollback()
        logger.exception("quickstart start failed for run %s", run_id)
        if self.request.retries >= self.max_retries:
            _give_up(session, run_id, exc)
            raise
        raise self.retry(exc=exc, countdown=15)
    finally:
        session.close()
    if batch_id is not None:
        start_lead_chain(str(batch_id), run_id)
    return str(batch_id) if batch_id else None


@celery_app.task(name="leadpilot.quickstart.draft", bind=True, max_retries=2)
def draft_quickstart(self, run_id: str):
    from app.services import quickstart  # noqa: PLC0415

    session = SessionLocal()
    try:
        return quickstart.draft_impl(session, uuid.UUID(run_id))
    except Exception as exc:
        session.rollback()
        logger.exception("quickstart drafting failed for run %s", run_id)
        if self.request.retries >= self.max_retries:
            _give_up(session, run_id, exc)
            raise
        raise self.retry(exc=exc, countdown=15)
    finally:
        session.close()


def enqueue(run_id) -> bool:
    """Publish `start` for a run. Never raises: a broker failure is logged and
    returns False, which the API reports instead of pretending it started.
    Tests monkeypatch this."""
    try:
        start_quickstart.apply_async(args=[str(run_id)], queue=QUEUE)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("could not enqueue quickstart run %s", run_id)
        return False
