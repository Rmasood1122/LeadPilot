"""Migrations 0033-0037 must produce exactly the schema the models declare.

Same copy-based technique as tests/test_revenue_migration.py and
tests/test_phone_migration.py: the full chain cannot run on SQLite (0008_m8c2
uses op.create_foreign_key, which SQLite has no ALTER for), so every table is
copied from the model metadata, the columns and tables these five migrations
ADD are removed from the copy, only the prerequisites are created, and then the
migrations run against that.

What this pins is the thing that actually breaks in production: a column added
to app/db/models.py and forgotten in the migration, or added with a different
type or nullability, which passes every test on a SQLite database built from
the models and then fails on a real PostgreSQL deployment.
"""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATIONS = [
    "0033_pipeline_health_score.py",
    "0034_reply_intelligence.py",
    "0035_voice_profile.py",
    "0036_displacement_alerts.py",
    "0037_roi_dashboard.py",
]

ADDED = {
    "strategies": ["pipeline_health_score", "health_band", "health_updated_at",
                   "health_message"],
    "inbound_replies": ["reply_category", "category_confidence", "ai_next_action",
                        "ai_draft_response", "classified_at", "reschedule_date"],
    "leads": ["estimated_deal_value"],
}
NEW_TABLES = ["voice_profiles", "displacement_alerts", "roi_snapshots"]

# Everything the five migrations reference, plus what those tables' foreign
# keys reference, so every FK resolves when the copy is created.
# whatsapp_templates is here because `messages` references it: the downgrade
# runs batch_alter_table, which reflects related tables, and an unreflectable
# FK target fails the copy-and-move.
_PREREQ = ["users", "products", "strategies", "lead_batches", "linkedin_accounts",
           "leads", "whatsapp_templates", "sequences", "messages",
           "inbound_replies"]


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
    for table_name, columns in ADDED.items():
        table = meta.tables[table_name]
        for name in columns:
            table._columns.remove(table.c[name])
    for name in NEW_TABLES:
        meta.remove(meta.tables[name])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 tuple(f["referred_columns"])) for f in inspector.get_foreign_keys(table)},
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
            for name in MIGRATIONS:
                _load(name).upgrade()
    yield sa.inspect(engine)
    engine.dispose()


def test_the_revision_chain_is_linear_and_starts_at_the_old_head():
    """A branched or misordered chain is an `alembic upgrade head` that fails
    on the deploy, not in CI."""
    modules = [_load(name) for name in MIGRATIONS]
    assert modules[0].down_revision == "0032_tool_integrations"
    for previous, nxt in zip(modules, modules[1:]):
        assert nxt.down_revision == previous.revision
    assert len({mod.revision for mod in modules}) == len(MIGRATIONS)


@pytest.mark.parametrize("table", NEW_TABLES)
def test_new_tables_match_the_models(from_models, from_migration, table):
    assert _describe(from_migration, table) == _describe(from_models, table)


@pytest.mark.parametrize("table", sorted(ADDED))
def test_added_columns_match_the_models(from_models, from_migration, table):
    assert (_describe(from_migration, table)["columns"]
            == _describe(from_models, table)["columns"])


def test_the_dedup_and_roi_indexes_exist(from_migration):
    """Both are load-bearing, not cosmetic: the displacement dedup check runs
    once per lead per sweep, and the ROI uniqueness is what makes the nightly
    snapshot idempotent."""
    alert_indexes = {i["name"] for i in from_migration.get_indexes("displacement_alerts")}
    assert "ix_displacement_alerts_lead_created" in alert_indexes
    roi_uniques = {tuple(sorted(u["column_names"]))
                   for u in from_migration.get_unique_constraints("roi_snapshots")}
    assert ("snapshot_date", "strategy_id") in roi_uniques
    voice_uniques = {tuple(sorted(u["column_names"]))
                     for u in from_migration.get_unique_constraints("voice_profiles")}
    assert ("product_id",) in voice_uniques


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    modules = [_load(name) for name in MIGRATIONS]
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            for module in modules:
                module.upgrade()
            for module in reversed(modules):
                module.downgrade()

    inspector = sa.inspect(engine)
    for table in NEW_TABLES:
        assert table not in inspector.get_table_names()
    for table, columns in ADDED.items():
        present = {c["name"] for c in inspector.get_columns(table)}
        assert not (set(columns) & present), table
    engine.dispose()
