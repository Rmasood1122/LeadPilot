"""F-REL-02 -- every name in CRITICAL_TASK_NAMES must be a registered Celery task.

monitoring._handle_task_failure sends the admin alert only when the failing
task's name is in CRITICAL_TASK_NAMES. Six of the eight names pointed at tasks
that do not exist (they were renamed to leadpilot.* long ago), so a failure in
the real pipeline / send tasks wrote a task_errors row and alerted nobody.
"""

from __future__ import annotations

from app.workers import monitoring
from app.workers.celery_app import celery_app


def _registered() -> set[str]:
    celery_app.loader.import_default_modules()
    return set(celery_app.tasks)


def test_every_critical_task_name_is_a_registered_task():
    dead = sorted(monitoring.CRITICAL_TASK_NAMES - _registered())
    assert dead == [], f"CRITICAL_TASK_NAMES names tasks that do not exist: {dead}"


def test_the_real_pipeline_and_send_tasks_are_critical():
    for name in ("leadpilot.run_pipeline", "leadpilot.run_verification",
                 "leadpilot.leads.source", "leadpilot.outreach.send",
                 "leadpilot.outreach.dispatch"):
        assert name in monitoring.CRITICAL_TASK_NAMES, name


def test_a_failure_in_a_real_send_task_raises_the_admin_alert(monkeypatch):
    """Through _handle_task_failure itself, not just the set."""
    alerts = []
    monkeypatch.setattr(monitoring, "_send_admin_failure_notification",
                        lambda name, etype, msg: alerts.append(name))
    monitoring._handle_task_failure(
        task_id="t1", task_name="leadpilot.outreach.send", args=(), kwargs={},
        exception=RuntimeError("boom"), tb_str="")
    assert alerts == ["leadpilot.outreach.send"]


def test_a_non_critical_task_does_not_raise_the_admin_alert(monkeypatch):
    alerts = []
    monkeypatch.setattr(monitoring, "_send_admin_failure_notification",
                        lambda name, etype, msg: alerts.append(name))
    monitoring._handle_task_failure(
        task_id="t2", task_name="leadpilot.ping", args=(), kwargs={},
        exception=RuntimeError("boom"), tb_str="")
    assert alerts == []
