"""Migration 0030 (Feature Group 8) must produce exactly the schema the models
declare. Same technique as tests/test_linkedin_migration.py: the added
sequences columns carry foreign keys, so the copy drops those constraints too.
"""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

ADDED = {"sequences": ["approval_requested_by_user_id", "approval_requested_at",
                       "approved_by_user_id", "approved_at", "approval_note",
                       "approval_payload_json"]}
NEW_TABLES = ["workspaces", "workspace_members", "workspace_invitations"]
_PREREQ = ["users", "products", "strategies", "sequences"]


def _load(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(root, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_prereqs(engine):
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    for table_name, cols in ADDED.items():
        table = meta.tables[table_name]
        for index in list(table.indexes):
            if any(c.name in cols for c in index.columns):
                table.indexes.discard(index)
        for constraint in list(table.constraints):
            if isinstance(constraint, sa.ForeignKeyConstraint) and any(
                    c in cols for c in constraint.column_keys):
                table.constraints.discard(constraint)
        for fk in list(table.foreign_keys):
            if fk.parent.name in cols:
                table.foreign_keys.discard(fk)
        for name in cols:
            table._columns.remove(table.c[name])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: {"columns": list(i["column_names"]), "unique": bool(i["unique"])}
                    for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 tuple(f["referred_columns"])) for f in inspector.get_foreign_keys(table)},
    }


@pytest.fixture()
def from_models(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    yield sa.inspect(engine)
    engine.dispose()


@pytest.fixture()
def from_migration(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _build_prereqs(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load("0030_workspaces.py").upgrade()
    yield sa.inspect(engine)
    engine.dispose()


@pytest.mark.parametrize("table", NEW_TABLES)
def test_new_tables_match(from_models, from_migration, table):
    assert _describe(from_migration, table) == _describe(from_models, table)


def test_sequence_columns_and_fks_match(from_models, from_migration):
    migrated, modelled = _describe(from_migration, "sequences"), _describe(from_models,
                                                                            "sequences")
    assert migrated["columns"] == modelled["columns"]
    assert migrated["fks"] == modelled["fks"]


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load("0030_workspaces.py")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    for table in NEW_TABLES:
        assert table not in inspector.get_table_names()
    assert "approved_at" not in {c["name"] for c in inspector.get_columns("sequences")}
    engine.dispose()
