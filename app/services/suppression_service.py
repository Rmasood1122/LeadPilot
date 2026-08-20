"""Compatibility module — suppression check for M8 send tasks.

Canonical implementation is app.workers.lead_tasks.is_suppressed (M2/M3:
checked at sourcing time AND at send time — compliance rule, no exceptions).
"""
from app.workers.lead_tasks import is_suppressed  # noqa: F401

__all__ = ["is_suppressed"]
