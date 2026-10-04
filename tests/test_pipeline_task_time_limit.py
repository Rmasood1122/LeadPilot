"""The pipeline TASKS get a task-sized time limit, not the per-step one.

Seen live on 2026-10-05: with the global Celery limit of 360s
(pipeline_step_timeout_seconds + 60) applied to the whole `run_pipeline` task,
a $3 run was SIGKILLed at step 63 ("Hard time limit (360s) exceeded"). A single
step takes ~25s, a budget-fitted run is 32 steps and a full one 144, so no run
could ever finish; the strategy stayed `researching` with nobody coming back.

The limit that is right for ONE step is wrong for the task that loops over all
of them. Offline: reads task metadata only, no broker, no network.
"""

from app.config import settings
from app.workers import tasks
from app.workers.celery_app import celery_app

# Steady-state cost of a step is ~25s (observed); the full flow is 144 steps.
WORST_CASE_FULL_RUN_SECONDS = 144 * 25


def test_run_pipeline_limit_outlasts_a_full_run():
    task = tasks.run_pipeline
    assert task.soft_time_limit == settings.pipeline_task_timeout_seconds
    assert task.soft_time_limit > WORST_CASE_FULL_RUN_SECONDS
    assert task.time_limit > task.soft_time_limit  # soft fires first -> clean retry/resume


def test_run_verification_has_the_task_sized_limit_too():
    task = tasks.run_verification
    assert task.soft_time_limit == settings.pipeline_task_timeout_seconds
    assert task.time_limit > task.soft_time_limit


def test_the_per_step_global_limit_is_unchanged_for_other_tasks():
    conf = celery_app.conf
    assert conf.task_soft_time_limit == settings.pipeline_step_timeout_seconds
    assert conf.task_time_limit == settings.pipeline_step_timeout_seconds + 60
    # and the pipeline tasks are no longer bound by it
    assert tasks.run_pipeline.time_limit > conf.task_time_limit


def test_redis_redelivery_window_is_past_the_hard_limit():
    """acks_late + Redis: a task unacked past visibility_timeout is handed to a
    second worker while the first is still running it."""
    window = celery_app.conf.broker_transport_options["visibility_timeout"]
    assert window > tasks.run_pipeline.time_limit
    assert window > tasks.run_verification.time_limit
