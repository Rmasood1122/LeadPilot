"""Compatibility module — canonical DB access for M8+ code.

M1–M7 code imports from `app.db.base`; M8 code was written against
`app.core.database`. Both must share ONE engine, ONE session factory and ONE
declarative Base (single Alembic metadata), so this module re-exports the
originals rather than creating parallel ones.
"""
from app.db.base import Base, engine, SessionLocal, get_db  # noqa: F401

__all__ = ["Base", "engine", "SessionLocal", "get_db"]
