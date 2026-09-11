"""Migration 0027 must produce exactly the schema the models declare.

Same copy-based technique as tests/test_linkedin_migration.py: every table is
copied so every foreign key resolves, 0027's own table and added columns are
removed from the copy, and only the prerequisites are created.
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

ADDED = {"leads": ["phone_consent_at", "phone_consent_source", "last_call_at",
                   "last_call_outcome"]}
_PREREQ = ["users", "products", "strategies", "lead_batches", "linkedin_accounts", "leads",
           "whatsapp_templates", "sequences", "messages"]


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
            _load("0027_phone_calling.py").upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_calls_table_matches(from_models, from_migration):
    assert _describe(from_migration, "calls") == _describe(from_models, "calls")


def test_lead_columns_match(from_models, from_migration):
    assert (_describe(from_migration, "leads")["columns"]
            == _describe(from_models, "leads")["columns"])


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load("0027_phone_calling.py")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    assert "calls" not in inspector.get_table_names()
    assert "phone_consent_at" not in {c["name"] for c in inspector.get_columns("leads")}
    engine.dispose()
