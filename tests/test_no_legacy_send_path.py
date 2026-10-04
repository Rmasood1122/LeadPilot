"""F-REL-01 -- the orphaned, non-atomic send path must not exist.

app/workers/send_tasks.py defined a second send task (read `sent_at IS NULL`,
send, then an unconditional UPDATE) alongside the canonical
outreach_tasks.send_message_impl, which claims the row atomically. It was
registered on the Celery app and routed to the outreach queue, so anything that
enqueued it by name would have bypassed the duplicate-send claim. Nothing
enqueued it; it is removed so nothing ever can.
"""

from __future__ import annotations

import importlib.util
import os

from app.workers.celery_app import celery_app

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_legacy_module_is_gone():
    assert not os.path.exists(os.path.join(ROOT, "app", "workers", "send_tasks.py"))
    assert importlib.util.find_spec("app.workers.send_tasks") is None


def test_it_is_not_in_the_worker_include_list():
    assert "app.workers.send_tasks" not in (celery_app.conf.include or [])


def test_it_has_no_route():
    routes = celery_app.conf.task_routes or {}
    assert not any("send_tasks" in str(key) for key in routes)


def test_no_task_is_registered_under_the_legacy_name():
    celery_app.loader.import_default_modules()
    assert not [n for n in celery_app.tasks if n.startswith("app.workers.send_tasks")]


def test_the_canonical_send_task_is_still_registered_and_routed():
    celery_app.loader.import_default_modules()
    assert "leadpilot.outreach.send" in celery_app.tasks
    assert "leadpilot.outreach.dispatch" in celery_app.tasks
    assert (celery_app.conf.task_routes or {}).get("leadpilot.outreach.*") == {
        "queue": "outreach"}
