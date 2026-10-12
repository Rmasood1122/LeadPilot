"""Migration 0087 creates exactly the table the model declares and adds the two
strategies columns (same technique as tests/test_daily_send_approval_migration.py)."""

from __future__ import annotations

import importlib.util
import os
import re

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0087_autopilot_launch.py"
TABLE = "autopilot_launches"
NEW_COLUMNS = ("send_time_plan_json", "send_time_override_json")
#: The bounded best-time learning query's index (review M7).
NEW_INDEX = ("messages", "ix_messages_status_sent_at")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(ROOT, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_prereqs(engine):
    """The tables as they were BEFORE 0087: strategies without its new columns."""
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    strategies = meta.tables["strategies"]
    for name in NEW_COLUMNS:
        strategies._columns.remove(strategies.c[name])
    messages = meta.tables[NEW_INDEX[0]]
    messages.indexes.discard(next(i for i in messages.indexes if i.name == NEW_INDEX[1]))
    # Every other table (the downgrade's SQLite batch copy of strategies reflects
    # the tables its foreign keys reach); never the table 0087 creates.
    meta.create_all(engine, tables=[t for name, t in meta.tables.items() if name != TABLE])


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


def _run(engine, fn):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            fn()


@pytest.fixture()
def from_models(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    yield sa.inspect(engine)
    engine.dispose()


@pytest.fixture()
def migrated(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _build_prereqs(engine)
    _run(engine, _load(MIGRATION).upgrade)
    yield engine
    engine.dispose()


def test_the_revision_follows_0085():
    module = _load(MIGRATION)
    assert module.revision == "0087_autopilot_launch"
    assert module.down_revision == "0086_inbound_reply_threading"


def test_table_matches_the_model(from_models, migrated):
    assert _describe(sa.inspect(migrated), TABLE) == _describe(from_models, TABLE)


def test_strategies_gets_both_columns_like_the_model(from_models, migrated):
    after = {c["name"]: c for c in sa.inspect(migrated).get_columns("strategies")}
    model = {c["name"]: c for c in from_models.get_columns("strategies")}
    for name in NEW_COLUMNS:
        assert str(after[name]["type"]) == str(model[name]["type"]) == "JSON"
        assert after[name]["nullable"] is True


def test_messages_gets_the_learning_index_like_the_model(from_models, migrated):
    table, name = NEW_INDEX
    after = {i["name"]: i["column_names"] for i in sa.inspect(migrated).get_indexes(table)}
    model = {i["name"]: i["column_names"] for i in from_models.get_indexes(table)}
    assert after[name] == model[name] == ["status", "sent_at"]


def test_one_row_per_strategy(migrated):
    uniques = sa.inspect(migrated).get_unique_constraints(TABLE)
    assert {"name": "uq_autopilot_launches_strategy_id", "column_names": ["strategy_id"]} in [
        {"name": u["name"], "column_names": u["column_names"]} for u in uniques]


def test_constraint_names_fit_postgres_63_chars():
    source = open(os.path.join(ROOT, "alembic", "versions", MIGRATION), encoding="utf-8").read()
    names = re.findall(r'name="([^"]+)"', source) + re.findall(r'"((?:ix|fk|uq)_[a-z_]+)"', source)
    assert names and all(len(n) <= 63 for n in names), [n for n in names if len(n) > 63]
    for constraint in Base.metadata.tables[TABLE].constraints:
        assert constraint.name is None or len(str(constraint.name)) <= 63


def test_downgrade_removes_table_and_columns(migrated):
    _run(migrated, _load(MIGRATION).downgrade)
    inspector = sa.inspect(migrated)
    assert TABLE not in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("strategies")}
    assert not columns & set(NEW_COLUMNS)
    indexes = {i["name"] for i in inspector.get_indexes(NEW_INDEX[0])}
    assert NEW_INDEX[1] not in indexes


def test_no_postgres_only_types():
    source = open(os.path.join(ROOT, "alembic", "versions", MIGRATION), encoding="utf-8").read()
    assert "postgresql." not in source and "JSONB" not in source


def test_activation_script_targets_this_head():
    from scripts import activate_with_keys as act

    from alembic.config import Config  # noqa: PLC0415
    from alembic.script import ScriptDirectory  # noqa: PLC0415

    # The activation script follows the single head; this migration is in its
    # history (a later migration may stack on top of it).
    script = ScriptDirectory.from_config(Config(os.path.join(ROOT, "alembic.ini")))
    assert script.get_heads() == [act.TARGET_REVISION]
    chain = {r.revision for r in script.walk_revisions("base", act.TARGET_REVISION)}
    assert "0087_autopilot_launch" in chain
