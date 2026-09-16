"""Migration 0057 (Part 1, Feature 5) must create exactly the table the model
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

MIGRATION = "0057_send_reviews.py"
TABLE = "send_reviews"
_PREREQ = ["users", "products", "strategies", "lead_batches", "linkedin_accounts",
           "leads", "whatsapp_templates", "sequences", "messages"]


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


def test_the_revision_follows_0056():
    module = _load(MIGRATION)
    assert module.revision == "0057_send_reviews"
    assert module.down_revision == "0056_mailbox_health"


def test_one_review_per_message_is_enforced_by_the_schema(from_migration):
    """Two reviews for one message would mean the send gate could read the
    approval or the rejection depending on row order."""
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints(TABLE)}
    assert uniques["send_review_message"] == ["message_id"]


def test_a_new_row_starts_pending(from_migration):
    columns = {c["name"]: c for c in from_migration.get_columns(TABLE)}
    assert "pending" in str(columns["status"]["default"])


def test_the_new_message_status_needs_no_column_change():
    """messages.status is a VARCHAR-backed enum, so AWAITING_REVIEW is a
    data-free addition -- the migration must not touch that column."""
    from app.db.models import Message, MessageStatus

    assert MessageStatus.AWAITING_REVIEW.value == "awaiting_review"
    column = Message.__table__.c.status
    assert getattr(column.type, "native_enum", True) is False
    assert "awaiting_review" in column.type.enums


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
