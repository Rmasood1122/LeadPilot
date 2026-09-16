"""Migration 0059 (Part 1, Feature 7) must create exactly the table the model
declares (create-only; tests/test_compliance_rules_migration.py technique)."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0059_reengagement_memory.py"
TABLE = "reengagement_plans"
_PREREQ = ["users", "products", "strategies", "lead_batches", "linkedin_accounts",
           "leads", "whatsapp_templates", "sequences", "messages", "inbound_replies"]


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


def _describe(inspector):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(TABLE)},
        "indexes": {i["name"]: list(i["column_names"]) for i in inspector.get_indexes(TABLE)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(TABLE)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"])
                for f in inspector.get_foreign_keys(TABLE)},
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


def test_the_revision_follows_0058():
    module = _load(MIGRATION)
    assert module.revision == "0059_reengagement_memory"
    assert module.down_revision == "0058_inbox_handling"


def test_one_plan_per_reply_is_enforced_by_the_schema(from_migration):
    """A webhook retry, a re-classification or two overlapping sweeps must not
    be able to produce two plans for one reply."""
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints(TABLE)}
    assert uniques["reengagement_plan_reply"] == ["source_reply_id"]


def test_a_new_row_starts_scheduled(from_migration):
    columns = {c["name"]: c for c in from_migration.get_columns(TABLE)}
    assert "scheduled" in str(columns["status"]["default"])


def test_the_plan_outlives_the_reply_and_the_sequence_that_made_it(from_migration):
    """A 90-day memory whose reply or strategy is deleted keeps the promise:
    only the LEAD reference cascades."""
    rules = {tuple(f["constrained_columns"]): f["options"].get("ondelete")
             for f in from_migration.get_foreign_keys(TABLE)}
    assert rules[("lead_id",)] == "CASCADE"
    assert rules[("source_reply_id",)] == "SET NULL"
    assert rules[("strategy_id",)] == "SET NULL"
    assert rules[("message_id",)] == "SET NULL"


def test_the_due_date_is_indexed_because_the_sweep_scans_it(from_migration):
    names = {i["name"] for i in from_migration.get_indexes(TABLE)}
    assert "ix_reengagement_plans_due_at" in names


def test_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration) == _describe(from_models)


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    assert TABLE not in sa.inspect(engine).get_table_names()
    engine.dispose()
