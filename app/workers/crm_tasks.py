"""Feature Group 4: CRM sync on the `default` queue.

It is integration I/O for one user at a time -- neither outreach volume nor
the learning loop -- so it runs with the other integration work.

  push_lead / push_deal       immediate push after an event (crm_sync.on_event)
  sync_connection             push-changed + pull for one connection
                              ("Sync now", and right after connecting)
  sync_all                    the 15-minute Beat sweep over every connection
  import_hubspot_deal         a deal created in HubSpot on a linked contact
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models import CrmConnection
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _session_call(fn, *args, **kwargs):
    session = SessionLocal()
    try:
        return fn(session, *args, **kwargs)
    finally:
        session.close()


@celery_app.task(name="app.workers.crm_tasks.push_lead")
def push_lead(user_id: str, lead_id: str) -> dict:
    from app.services import crm_sync  # noqa: PLC0415

    return _session_call(crm_sync.push_lead, uuid.UUID(user_id), lead_id)


@celery_app.task(name="app.workers.crm_tasks.push_deal")
def push_deal(user_id: str, deal_id: str) -> dict:
    from app.services import crm_sync  # noqa: PLC0415

    return _session_call(crm_sync.push_deal, uuid.UUID(user_id), deal_id)


@celery_app.task(name="app.workers.crm_tasks.sync_connection")
def sync_connection(connection_id: str, full: bool = False) -> dict:
    from app.services import crm_sync  # noqa: PLC0415

    return _session_call(crm_sync.sync_connection, connection_id, full=full)


def sync_all_impl(session) -> dict:
    from app.services import crm_sync  # noqa: PLC0415

    ids = session.execute(select(CrmConnection.id)
                          .where(CrmConnection.status != "revoked")).scalars().all()
    ok = failed = 0
    for connection_id in ids:
        try:
            result = crm_sync.sync_connection(session, connection_id)
            ok += int(result.get("status") == "ok")
            failed += int(result.get("status") == "error")
        except Exception:
            session.rollback()
            failed += 1
            logger.exception("crm sweep: connection %s failed", connection_id)
    return {"connections": len(ids), "ok": ok, "failed": failed}


@celery_app.task(name="app.workers.crm_tasks.sync_all")
def sync_all() -> dict:
    return _session_call(sync_all_impl)


@celery_app.task(name="app.workers.crm_tasks.import_hubspot_deal")
def import_hubspot_deal(user_id: str, remote_deal_id: str) -> str:
    from app.services import crm_sync  # noqa: PLC0415

    return _session_call(crm_sync.import_hubspot_deal, uuid.UUID(user_id), remote_deal_id)


# ---- publish points (tests patch these: tests/conftest.py::queued_jobs) ----


def _publish(task, *args) -> bool:
    try:
        task.apply_async(args=[str(a) if not isinstance(a, bool) else a for a in args],
                         retry=False)
        return True
    except Exception:
        logger.exception("crm: could not enqueue %s%s", task.name, args)
        return False


def enqueue_push(kind: str, user_id, local_id) -> bool:
    return _publish(push_lead if kind == "lead" else push_deal, user_id, local_id)


def enqueue_sync(connection_id, full: bool = False) -> bool:
    return _publish(sync_connection, connection_id, full)


def enqueue_import(user_id, remote_deal_id) -> bool:
    return _publish(import_hubspot_deal, user_id, remote_deal_id)
