"""Migration 0076 (F06 Quickstart) must create exactly the tables the models
declare (create-only; the tests/test_send_reviews_migration.py technique)."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0076_quickstart.py"
TABLES = ["quickstart_runs", "quickstart_drafts"]
_PREREQ = ["users", "products", "workspaces", "client_workspaces", "strategies",
           "lead_batches", "linkedin_accounts", "leads"]


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
def from_migration(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _build_prereqs(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_the_revision_follows_0075():
    module = _load(MIGRATION)
    assert module.revision == "0076_quickstart"
    assert module.down_revision == "0075_deliverability_autopilot"


@pytest.mark.parametrize("table", TABLES)
def test_table_matches_the_model(from_models, from_migration, table):
    assert _describe(from_migration, table) == _describe(from_models, table)


def test_one_draft_per_lead_per_run_is_enforced_by_the_schema(from_migration):
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints("quickstart_drafts")}
    assert uniques["uq_quickstart_draft_run_lead"] == ["lead_id", "run_id"]


def test_drafts_go_with_their_lead_and_account(from_migration):
    """GDPR: a draft quotes the person -- it must not outlive the lead row or
    the account that owns it."""
    fks = {(tuple(f["constrained_columns"]), f["referred_table"]):
           (f.get("options") or {}).get("ondelete")
           for f in from_migration.get_foreign_keys("quickstart_drafts")}
    assert fks[(("lead_id",), "leads")] == "CASCADE"
    assert fks[(("user_id",), "users")] == "CASCADE"


def test_nothing_in_the_migration_touches_messages():
    """The review-only property starts at the schema: no messages column, no
    sequence link."""
    source = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "alembic", "versions", MIGRATION), encoding="utf-8").read()
    code = source.split('"""', 2)[2]
    assert "messages" not in code and "sequence" not in code


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    names = sa.inspect(engine).get_table_names()
    assert not set(TABLES) & set(names)
    assert {"leads", "strategies", "products"} <= set(names)
    engine.dispose()
