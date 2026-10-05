"""Migration 0069 adds exactly users.full_name, nullable, and removes it on downgrade."""
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
    spec = importlib.util.spec_from_file_location(
        "mig0069", os.path.join(root, "alembic", "versions", "0069_user_full_name.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _users_without_name(engine):
    meta = sa.MetaData()
    Base.metadata.tables["users"].to_metadata(meta)
    meta.tables["users"]._columns.remove(meta.tables["users"].c.full_name)
    meta.create_all(engine)


def test_chain_and_column(tmp_path):
    mod = _load()
    assert mod.revision == "0069_user_full_name"
    assert mod.down_revision == "0068_linkedin_network"
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    _users_without_name(engine)
    assert "full_name" not in {c["name"] for c in sa.inspect(engine).get_columns("users")}
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.upgrade()
    col = {c["name"]: c for c in sa.inspect(engine).get_columns("users")}["full_name"]
    assert col["nullable"] is True
    assert getattr(col["type"], "length", None) == 120
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            mod.downgrade()
    assert "full_name" not in {c["name"] for c in sa.inspect(engine).get_columns("users")}
    engine.dispose()
