"""Migration 0079 (F09 Pilot Mode) must create exactly the tables the models
declare (create-only; the tests/test_quickstart_migration.py technique), and
the two uniqueness rules the feature depends on must be in the schema."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0079_pilot_mode.py"
TABLES = ["pilots", "pilot_scorecards"]
_PREREQ = ["users"]


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
        "indexes": {i["name"]: list(i["column_names"]) for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 (f.get("options") or {}).get("ondelete"))
                for f in inspector.get_foreign_keys(table)},
    }


@pytest.fixture()
def from_models(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    yield sa.inspect(engine)
    engine.dispose()


@pytest.fixture()
def migrated(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
    yield engine
    engine.dispose()


def test_the_revision_follows_0076():
    module = _load(MIGRATION)
    assert module.revision == "0079_pilot_mode"
    assert module.down_revision == "0078_spend_guard"


@pytest.mark.parametrize("table", TABLES)
def test_table_matches_the_model(from_models, migrated, table):
    assert _describe(sa.inspect(migrated), table) == _describe(from_models, table)


def test_uniqueness_rules_are_in_the_schema(migrated):
    inspector = sa.inspect(migrated)
    pilots = {u["name"]: u["column_names"] for u in inspector.get_unique_constraints("pilots")}
    cards = {u["name"]: sorted(u["column_names"])
             for u in inspector.get_unique_constraints("pilot_scorecards")}
    assert pilots["uq_pilots_active_owner_id"] == ["active_owner_id"]
    assert cards["uq_pilot_scorecard_week"] == ["pilot_id", "week"]


def test_pilots_go_with_their_account(migrated):
    fks = {tuple(f["constrained_columns"]): (f.get("options") or {}).get("ondelete")
           for f in sa.inspect(migrated).get_foreign_keys("pilots")}
    assert fks[("user_id",)] == "CASCADE"
    assert fks[("started_by_user_id",)] == "SET NULL"


def test_downgrade_drops_both_tables(migrated):
    with migrated.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).downgrade()
    names = set(sa.inspect(migrated).get_table_names())
    assert not names & set(TABLES)
    assert "users" in names
