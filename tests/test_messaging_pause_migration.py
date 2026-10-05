"""Migration 0072 only ADDS four nullable columns and is fully reversible."""

from __future__ import annotations

import importlib.util
import os

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base


def _load():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "alembic", "versions", "0072_messaging_pause.py")
    spec = importlib.util.spec_from_file_location("mig0072", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'x.db'}")
    meta = sa.MetaData()
    for t in ("users", "leads"):
        sa.Table(t, meta, sa.Column("id", sa.Integer, primary_key=True))
    meta.create_all(engine)
    return engine


def _cols(engine, table):
    return {c["name"]: c for c in sa.inspect(engine).get_columns(table)}


def test_chain_position():
    mod = _load()
    assert mod.revision == "0072_messaging_pause"
    assert mod.down_revision == "0071_voice_interviews"


def test_upgrade_adds_nullable_columns_matching_the_models(tmp_path):
    engine, mod = _engine(tmp_path), _load()
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
    for table, model in (("users", m.User), ("leads", m.Lead)):
        cols = _cols(engine, table)
        for name in ("messaging_paused_at", "messaging_paused_reason"):
            assert name in cols and cols[name]["nullable"]
            assert name in model.__table__.c


def test_downgrade_removes_them(tmp_path):
    engine, mod = _engine(tmp_path), _load()
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.downgrade()
    for table in ("users", "leads"):
        assert "messaging_paused_at" not in _cols(engine, table)
