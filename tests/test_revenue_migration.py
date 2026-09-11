"""Migration 0028 must produce exactly the schema the models declare.

Same copy-based technique as tests/test_phone_migration.py: every table is
copied so every foreign key resolves, 0028's added columns are removed from
the copy, and only the prerequisites are created.
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

ADDED = {
    "messages": ["opened_at", "open_count"],
    "strategies": ["smart_send_time", "send_windows_json", "send_windows_computed_at"],
}
NEW_TABLES = ["campaign_costs", "api_usage", "reply_sentiment_weeks"]
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
            _load("0028_revenue_analytics.py").upgrade()
    yield sa.inspect(engine)
    engine.dispose()


@pytest.mark.parametrize("table", NEW_TABLES)
def test_new_tables_match(from_models, from_migration, table):
    assert _describe(from_migration, table) == _describe(from_models, table)


@pytest.mark.parametrize("table", sorted(ADDED))
def test_added_columns_match(from_models, from_migration, table):
    assert (_describe(from_migration, table)["columns"]
            == _describe(from_models, table)["columns"])


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load("0028_revenue_analytics.py")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    for table in NEW_TABLES:
        assert table not in inspector.get_table_names()
    assert "open_count" not in {c["name"] for c in inspector.get_columns("messages")}
    assert "smart_send_time" not in {c["name"] for c in inspector.get_columns("strategies")}
    engine.dispose()
