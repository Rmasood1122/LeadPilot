"""Compatibility package — per-model import paths used by M8 code.

The canonical ORM models live in app/db/models.py (single file, single Base,
single Alembic metadata). These modules re-export them so both import styles
resolve to the SAME classes.
"""
