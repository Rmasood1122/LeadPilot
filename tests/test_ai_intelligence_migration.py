"""Migration 0024 must produce exactly the schema the models declare.

Same technique as tests/test_meeting_prep_migration.py. 0024 both creates
tables and ADDS columns to `strategies` and `leads`, so those two
prerequisites are built WITHOUT the added columns (and without the index on
one of them) -- otherwise the comparison would pass even if upgrade() added
nothing.
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

NEW_TABLES = ["strategy_model_outputs", "strategy_uncertain_zones", "strategy_versions"]
ADDED = {
    "strategies": ["market_signals_json", "market_signals_fetched_at",
                   "consensus_status", "last_mutation_at"],
    "leads": ["ai_booking_likelihood", "ai_score_reason", "ai_score_factors",
              "ai_scored_at"],
}
# linkedin_accounts: leads carries a foreign key to it since 0026, and the
# batch-mode downgrade reflects leads -- which reflects every table it
# references. At the real 0024 revision neither exists; here the copy keeps
# later columns, so the referenced table has to exist for reflection.
_PREREQ = ["users", "products", "strategies", "lead_batches", "linkedin_accounts", "leads"]


def _load(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(root, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _build_prereqs(engine):
    """Prerequisites as they stood before 0024, built from a COPY of the
    metadata. Mutating the shared Base.metadata and restoring it is not safe
    here: re-appending an index=True column makes SQLAlchemy create a second
    Index object with the same name, and every later create_all in the
    process then fails with "index already exists"."""
    # EVERY table is copied so every foreign key in the copy resolves (leads
    # references linkedin_accounts since 0026); only _PREREQ is created.
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    for table_name, cols in ADDED.items():
        table = meta.tables[table_name]
        for index in list(table.indexes):
            if any(c.name in cols for c in index.columns):
                table.indexes.discard(index)
        for name in cols:
            table._columns.remove(table.c[name])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


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
            _load("0024_ai_intelligence.py").upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_prerequisites_really_lack_the_columns(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'pre.db'}")
    _build_prereqs(engine)
    cols = {c["name"] for c in sa.inspect(engine).get_columns("leads")}
    assert "ai_booking_likelihood" not in cols
    engine.dispose()
    assert "ai_booking_likelihood" in Base.metadata.tables["leads"].c   # restored


@pytest.mark.parametrize("table", NEW_TABLES + ["strategies", "leads"])
def test_columns_match(table, from_models, from_migration):
    assert _describe(from_migration, table)["columns"] == _describe(from_models, table)["columns"]


@pytest.mark.parametrize("table", NEW_TABLES + ["leads"])
def test_indexes_match(table, from_models, from_migration):
    assert _describe(from_migration, table)["indexes"] == _describe(from_models, table)["indexes"]


@pytest.mark.parametrize("table", NEW_TABLES)
def test_uniques_and_fks_match(table, from_models, from_migration):
    a, b = _describe(from_migration, table), _describe(from_models, table)
    assert a["uniques"] == b["uniques"]
    assert a["fks"] == b["fks"]


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load("0024_ai_intelligence.py")
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    assert not set(NEW_TABLES) & set(inspector.get_table_names())
    assert "ai_booking_likelihood" not in {c["name"] for c in inspector.get_columns("leads")}
    engine.dispose()
