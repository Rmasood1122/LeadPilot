"""Migration 0077 (F04 Reply Copilot) must create exactly the tables the models
declare (create-only; the tests/test_quickstart_migration.py technique)."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0077_reply_copilot.py"
TABLES = ["reply_drafts", "reply_copilot_settings"]
_PREREQ = ["users", "products", "workspaces", "client_workspaces", "strategies",
           "lead_batches", "linkedin_accounts", "leads", "sequences", "whatsapp_templates",
           "messages", "inbound_replies"]


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


def test_the_revision_follows_0076():
    module = _load(MIGRATION)
    assert module.revision == "0077_reply_copilot"
    assert module.down_revision == "0076_quickstart"


@pytest.mark.parametrize("table", TABLES)
def test_table_matches_the_model(from_models, from_migration, table):
    assert _describe(from_migration, table) == _describe(from_models, table)


def test_one_draft_per_reply_is_enforced_by_the_schema(from_migration):
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints("reply_drafts")}
    assert uniques["uq_reply_drafts_reply_id"] == ["reply_id"]


def test_drafts_go_with_their_reply_lead_and_account(from_migration):
    """GDPR: a draft quotes the person -- it must not outlive the reply, the
    lead row or the account that owns it. The queued message outlives it."""
    fks = {(tuple(f["constrained_columns"]), f["referred_table"]):
           (f.get("options") or {}).get("ondelete")
           for f in from_migration.get_foreign_keys("reply_drafts")}
    assert fks[(("reply_id",), "inbound_replies")] == "CASCADE"
    assert fks[(("lead_id",), "leads")] == "CASCADE"
    assert fks[(("user_id",), "users")] == "CASCADE"
    assert fks[(("message_id",), "messages")] == "SET NULL"


def test_auto_send_defaults_off_in_the_schema(from_migration):
    columns = {c["name"]: c for c in from_migration.get_columns("reply_copilot_settings")}
    default = str(columns["auto_send_meeting_time"]["default"]).lower()
    assert default in ("0", "false", "'0'", "'false'")


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
    assert {"leads", "messages", "inbound_replies"} <= set(names)
    engine.dispose()
