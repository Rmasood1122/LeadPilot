"""Compatibility module — `app.db.session` alias used by the M7 devices API.

Single source of truth lives in app/db/base.py.
"""
from app.db.base import engine, SessionLocal, get_db  # noqa: F401

__all__ = ["engine", "SessionLocal", "get_db"]
