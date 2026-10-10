"""Migration 0074 (F02 Signal Radar) must create exactly the table the model
declares (create-only; tests/test_consent_migration.py technique), sit on the
current head, and round-trip."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0074_signal_radar.py"
TABLE = "lead_signals"
_PREREQ = ["users", "products", "workspaces", "client_workspaces", "strategies",
           "lead_batches", "linkedin_accounts", "leads"]
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(_ROOT, "alembic", "versions", name))
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
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 f["options"].get("ondelete"))
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


def test_the_revision_follows_0073():
    module = _load(MIGRATION)
    assert module.revision == "0074_signal_radar"
    assert module.down_revision == "0073_waterfall_enrichment"


def test_it_is_the_single_head():
    script = ScriptDirectory.from_config(Config(os.path.join(_ROOT, "alembic.ini")))
    assert script.get_heads() == ["0074_signal_radar"]


def test_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration) == _describe(from_models)


def test_signals_go_with_the_lead_and_the_account(from_migration):
    """Derived personal data: CASCADE, unlike the consent ledger which must
    outlive the erasure it proves."""
    rules = {tuple(f["constrained_columns"]): f["options"].get("ondelete")
             for f in from_migration.get_foreign_keys(TABLE)}
    assert rules == {("lead_id",): "CASCADE", ("user_id",): "CASCADE"}


def test_one_row_per_event_per_lead(from_migration):
    uniques = {u["name"]: u["column_names"]
               for u in from_migration.get_unique_constraints(TABLE)}
    assert uniques["uq_lead_signals_lead_dedupe"] == ["lead_id", "dedupe_key"]


def test_the_facts_a_signal_needs_are_not_nullable(from_migration):
    columns = {c["name"]: c for c in from_migration.get_columns(TABLE)}
    for name in ("signal_type", "source", "title", "observed_at", "expires_at",
                 "confidence", "dedupe_key", "user_id", "lead_id"):
        assert columns[name]["nullable"] is False, name
    assert columns["source_url"]["nullable"] is True, "Apollo signals have no public link"


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
            module.upgrade()
    assert TABLE in sa.inspect(engine).get_table_names()
    engine.dispose()
