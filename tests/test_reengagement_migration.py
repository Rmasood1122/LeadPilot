"""Migration 0048 (Feature 5) must produce exactly the schema the models
declare: the new reengagement_attempts table, four strategies columns and
messages.origin. Same technique as tests/test_workspaces_migration.py -- the
columns 0048 ADDS are removed from the prerequisite tables, so the migration
has real work to do rather than comparing a table to itself."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0048_reengagement.py"
TABLE = "reengagement_attempts"
ADDED = {
    "strategies": ["reengagement_enabled", "reengagement_delay_days",
                   "reengagement_daily_cap", "reengagement_weekly_cap"],
    "messages": ["origin"],
}
# `workspaces` and `client_workspaces` are prerequisites because
# `strategies` gained a foreign key to the latter in migration 0063
# (Part 1 Feature 11). Without them the pre-migration `strategies`
# table references a table that does not exist, which SQLite refuses.
_PREREQ = ["users", "products", "workspaces", "client_workspaces", "strategies", "lead_batches", "leads", "whatsapp_templates",
           "linkedin_accounts", "sequences", "sequence_enrollments", "messages"]


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
        for name in cols:
            table._columns.remove(table.c[name])
    wanted = [t for t in _PREREQ if t in meta.tables]
    # Pull in anything the prerequisites point at, so their FKs resolve.
    needed = set(wanted)
    changed = True
    while changed:
        changed = False
        for name in list(needed):
            for fk in meta.tables[name].foreign_keys:
                target = fk.column.table.name
                if target not in needed:
                    needed.add(target)
                    changed = True
    meta.create_all(engine, tables=[t for t in meta.sorted_tables if t.name in needed])


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: {"columns": list(i["column_names"]), "unique": bool(i["unique"])}
                    for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"])
                for f in inspector.get_foreign_keys(table)},
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
            _load(MIGRATION).upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_the_revision_follows_0047():
    module = _load(MIGRATION)
    assert module.revision == "0048_reengagement"
    assert module.down_revision == "0047_sequence_reviews"


def test_new_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration, TABLE) == _describe(from_models, TABLE)


@pytest.mark.parametrize("table", sorted(ADDED))
def test_added_columns_and_indexes_match(from_models, from_migration, table):
    migrated, modelled = _describe(from_migration, table), _describe(from_models, table)
    assert migrated["columns"] == modelled["columns"]
    assert migrated["indexes"] == modelled["indexes"]


def test_added_strategy_columns_carry_server_defaults(from_migration):
    """An ALTER adding a NOT NULL column to a table that already has rows needs
    a server default, and that default is what every existing campaign gets --
    so it must exist, and the toggle's must be off."""
    columns = {c["name"]: c for c in from_migration.get_columns("strategies")}
    for name in ADDED["strategies"]:
        assert columns[name]["default"] is not None, f"{name} has no server default"
    assert str(columns["reengagement_enabled"]["default"]).strip("'\"").lower() in {"0", "false"}


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    assert TABLE not in inspector.get_table_names()
    assert "origin" not in {c["name"] for c in inspector.get_columns("messages")}
    assert "reengagement_enabled" not in {c["name"] for c in inspector.get_columns("strategies")}
    engine.dispose()
