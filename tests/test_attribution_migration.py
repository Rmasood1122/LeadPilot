"""Migration 0060 (Part 1, Feature 8) must create exactly the table the model
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

MIGRATION = "0060_attribution_ledger.py"
TABLE = "attribution_entries"
# `workspaces` and `client_workspaces` are prerequisites because
# `strategies` gained a foreign key to the latter in migration 0063
# (Part 1 Feature 11). Without them the pre-migration `strategies`
# table references a table that does not exist, which SQLite refuses.
_PREREQ = ["users", "products", "workspaces", "client_workspaces", "strategies", "lead_batches", "linkedin_accounts",
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


def test_the_revision_follows_0059():
    module = _load(MIGRATION)
    assert module.revision == "0060_attribution_ledger"
    assert module.down_revision == "0059_reengagement_memory"


def test_one_entry_per_outcome_is_enforced_by_the_schema(from_migration):
    """This is what makes the quarter-hourly sweep safe to run forever: it
    can never double-credit an outcome."""
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints(TABLE)}
    assert uniques["attribution_outcome"] == ["outcome_id", "outcome_kind"]


def test_nothing_cascades_away_the_record_of_what_earned_an_outcome(from_migration):
    """Every reference is SET NULL. A ledger that deletes itself when the
    prospect or the message is removed cannot answer 'what worked last year?'."""
    rules = {tuple(f["constrained_columns"]): f["options"].get("ondelete")
             for f in from_migration.get_foreign_keys(TABLE)}
    assert set(rules.values()) == {"SET NULL"}


def test_the_credited_message_may_be_null(from_migration):
    """'Nothing was sent before this' is an answer, and the schema has to be
    able to hold it."""
    columns = {c["name"]: c for c in from_migration.get_columns(TABLE)}
    assert columns["message_id"]["nullable"] is True
    assert columns["method"]["nullable"] is False


def test_the_outcome_time_is_indexed_because_the_ledger_sorts_by_it(from_migration):
    names = {i["name"] for i in from_migration.get_indexes(TABLE)}
    assert "ix_attribution_entries_outcome_at" in names


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
