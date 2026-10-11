"""Migration 0081 creates exactly the table the model declares (create-only;
same technique as tests/test_champion_tracker_migration.py)."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0081_daily_send_approval.py"
TABLE = "daily_send_approvals"
_PREREQ = ["users"]


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
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: list(i["column_names"]) for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 f["options"].get("ondelete"))
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


def test_the_revision_follows_0080_champion_tracker():
    module = _load(MIGRATION)
    assert module.revision == "0081_daily_send_approval"
    assert module.down_revision == "0080_champion_tracker"


def test_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration, TABLE) == _describe(from_models, TABLE)


def test_one_row_per_account_per_local_day(from_migration):
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints(TABLE)}
    assert uniques["uq_daily_send_approval_user_date"] == ["local_date", "user_id"]


def test_rows_go_with_the_account_and_keep_without_the_approver(from_migration):
    rules = {(tuple(f["constrained_columns"]), f["referred_table"]): f["options"].get("ondelete")
             for f in from_migration.get_foreign_keys(TABLE)}
    assert rules[(("user_id",), "users")] == "CASCADE"
    assert rules[(("decided_by_user_id",), "users")] == "SET NULL"


def test_nothing_existing_is_altered():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source = open(os.path.join(root, "alembic", "versions", MIGRATION), encoding="utf-8").read()
    code = source.split('"""', 2)[2]
    assert "alter_column" not in code and "add_column" not in code
    assert "drop_column" not in code


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    names = set(sa.inspect(engine).get_table_names())
    assert TABLE not in names and "users" in names
    engine.dispose()
