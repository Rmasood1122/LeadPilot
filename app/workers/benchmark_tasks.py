"""Feature 6 — the nightly benchmark snapshot (learning queue).

Read-only over outcomes and messages; writes only benchmark_buckets, replacing
it in one transaction, so a re-run or an overlapping run leaves one consistent
snapshot. See app/services/benchmarks.py.
"""

from __future__ import annotations

from app.db.base import SessionLocal
from app.services import benchmarks
from app.workers.celery_app import celery_app


def compute_benchmarks_impl(session) -> dict:
    return benchmarks.compute_snapshot(session)


@celery_app.task(name="app.workers.benchmark_tasks.compute_benchmarks")
def compute_benchmarks() -> dict:
    session = SessionLocal()
    try:
        return compute_benchmarks_impl(session)
    finally:
        session.close()
