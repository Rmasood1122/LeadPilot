"""
TaskError model — stores Celery task failures for admin review.

Populated by workers.monitoring.register_task_failure_signal().
"""
from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class TaskError(Base):
    __tablename__ = "task_errors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_name = Column(String(256), nullable=False, index=True)
    task_id = Column(String(256), nullable=True, index=True)
    args_summary = Column(Text, nullable=True)
    error_type = Column(String(128), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    traceback = Column(Text, nullable=True)
    ts = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, index=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(256), nullable=True)  # admin user email
    resolution_note = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<TaskError {self.task_name} at {self.ts}>"
