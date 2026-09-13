"""Migration 0042 (Feature A2 audit trail) must produce exactly the schema the
model declares. SQLite skips the PostgreSQL-only append-only trigger; its
presence on PostgreSQL is pinned by source inspection below, and the ORM guard
that applies everywhere is covered in tests/test_activity_audit_trail.py."""

from __future__ import annotations

import importlib.util
import inspect
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0042_activity_audit_trail.py"
TABLE = "activity_audit_events"


def _load(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(root, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _describe(inspector):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(TABLE)},
        "indexes": {i["name"]: list(i["column_names"]) for i in inspector.get_indexes(TABLE)},
        "uniques": {tuple(sorted(u["column_names"]))
                    for u in inspector.get_unique_constraints(TABLE)},
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
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_the_revision_follows_0041():
    module = _load(MIGRATION)
    assert module.revision == "0042_activity_audit_trail"
    assert module.down_revision == "0041_claim_verification_log"


def test_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration) == _describe(from_models)


def test_a_chain_position_can_be_held_by_one_record_only(from_migration):
    uniques = _describe(from_migration)["uniques"]
    assert ("seq_no", "user_id") in uniques
    assert ("outcome_ref",) in uniques


def test_hashed_references_carry_no_foreign_keys(from_migration):
    """An ON DELETE SET NULL would rewrite hashed content on a GDPR erase and
    make the chain report tampering that never happened."""
    assert from_migration.get_foreign_keys(TABLE) == []


def test_postgres_gets_the_append_only_trigger():
    source = inspect.getsource(_load(MIGRATION))
    assert "BEFORE UPDATE OR DELETE ON activity_audit_events" in source
    assert "append-only" in source


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    assert TABLE not in sa.inspect(engine).get_table_names()
    engine.dispose()
