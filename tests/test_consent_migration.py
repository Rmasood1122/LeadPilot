"""Migration 0061 (Part 1, Feature 9) must create exactly the table the model
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

MIGRATION = "0061_consent_ledger.py"
TABLE = "consent_events"
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


def test_the_revision_follows_0060():
    module = _load(MIGRATION)
    assert module.revision == "0061_consent_ledger"
    assert module.down_revision == "0060_attribution_ledger"


def test_the_erasure_record_survives_the_erasure(from_migration):
    """lead_id is SET NULL, not CASCADE. A ledger that deletes itself with
    the prospect record cannot prove the deletion request was honoured --
    which is the one moment it exists for."""
    rules = {tuple(f["constrained_columns"]): f["options"].get("ondelete")
             for f in from_migration.get_foreign_keys(TABLE)}
    assert rules[("lead_id",)] == "SET NULL"
    assert set(rules.values()) == {"SET NULL"}


def test_the_identifier_is_stored_and_indexed(from_migration):
    """After the lead is gone the suppression still has to be matchable, and
    searchable: when someone writes 'I asked you to stop', the address is the
    only thing you have."""
    columns = {c["name"] for c in from_migration.get_columns(TABLE)}
    assert "identifier" in columns
    names = {i["name"] for i in from_migration.get_indexes(TABLE)}
    assert "ix_consent_events_identifier" in names


def test_the_ledger_read_is_indexed_as_it_is_actually_queried(from_migration):
    """Every read is "WHERE user_id = ? ORDER BY ts DESC"."""
    indexes = {i["name"]: list(i["column_names"])
               for i in from_migration.get_indexes(TABLE)}
    assert indexes["ix_consent_events_user_ts"] == ["user_id", "ts"]


def test_the_facts_that_make_an_event_meaningful_are_not_nullable(from_migration):
    columns = {c["name"]: c for c in from_migration.get_columns(TABLE)}
    for name in ("kind", "channel", "source", "ts"):
        assert columns[name]["nullable"] is False


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
