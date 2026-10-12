"""Migration 0089 (voice twin): two tables and four `calls` columns matching
the model; calls.lead_id becomes nullable; existing calls become `outbound`;
names fit PostgreSQL's 63-character limit; downgrade round-trips (dropping
lead-less inbound calls, as documented)."""

from __future__ import annotations

import importlib.util
import os
import re

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = "0089_voice_twin.py"
TABLES = ("voice_clones", "voice_twin_settings", "voice_clone_deletions")
ADDED = ("direction", "voice_clone_used", "from_number", "control_url")


def _load(name=MIGRATION):
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(ROOT, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(engine, *steps):
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            for step in steps:
                step()


def _engine_before(tmp_path):
    """The schema as it was at 0088: every model table except the two 0089
    creates, `calls` without its four new columns and with lead_id NOT NULL."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'vt.db'}")
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    calls = meta.tables["calls"]
    for name in ADDED:
        calls._columns.remove(calls.c[name])
    calls.c.lead_id.nullable = False
    meta.create_all(engine, tables=[t for t in meta.sorted_tables if t.name not in TABLES])
    return engine


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: list(i["column_names"]) for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 f["options"].get("ondelete")) for f in inspector.get_foreign_keys(table)},
    }


def test_the_revision_follows_0088():
    module = _load()
    assert module.revision == "0089_voice_twin"
    assert module.down_revision == "0088_local_business"


def test_upgrade_matches_the_model_and_keeps_existing_calls_outbound(tmp_path):
    engine = _engine_before(tmp_path)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO calls (id, lead_id, provider, to_number, status, created_at, "
            "updated_at) VALUES ('c1', 'l1', 'vapi', '+1555', 'ended', CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)"))
    _run(engine, _load().upgrade)
    with engine.begin() as connection:
        row = connection.execute(sa.text(
            "SELECT direction, voice_clone_used FROM calls WHERE id = 'c1'")).one()
    assert row[0] == "outbound" and not row[1]
    reference = sa.create_engine(f"sqlite:///{tmp_path / 'model.db'}")
    Base.metadata.create_all(reference)
    got, want = sa.inspect(engine), sa.inspect(reference)
    for table in TABLES:
        assert _describe(got, table) == _describe(want, table), table
    assert _describe(got, "calls")["columns"] == _describe(want, "calls")["columns"]
    assert _describe(got, "calls")["columns"]["lead_id"]["nullable"] is True
    engine.dispose()
    reference.dispose()


def test_constraint_names_fit_postgres():
    source = open(os.path.join(ROOT, "alembic", "versions", MIGRATION), encoding="utf-8").read()
    names = re.findall(r'name="([^"]+)"', source) + re.findall(r'"(ix_[a-z_]+)"', source)
    assert names and all(len(n) <= 63 for n in names), names
    for table in TABLES:
        for constraint in Base.metadata.tables[table].constraints:
            assert constraint.name is None or len(constraint.name) <= 63
    assert "postgresql." not in source and "JSONB" not in source


def test_no_audio_column_anywhere():
    """Guard 6 at the schema level: there is nowhere to put a recording."""
    for table in TABLES:
        for column in Base.metadata.tables[table].columns:
            assert not isinstance(column.type, sa.LargeBinary), (table, column.name)
            assert "audio" not in column.name, (table, column.name)


def test_downgrade_round_trips_and_drops_lead_less_calls(tmp_path):
    engine = _engine_before(tmp_path)
    module = _load()
    _run(engine, module.upgrade)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO calls (id, lead_id, provider, to_number, status, direction, "
            "voice_clone_used, created_at, updated_at) VALUES ('in1', NULL, 'vapi', '', "
            "'ended', 'inbound', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    _run(engine, module.downgrade)
    inspector = sa.inspect(engine)
    for table in TABLES:
        assert table not in inspector.get_table_names()
    columns = {c["name"]: c for c in inspector.get_columns("calls")}
    assert not set(ADDED) & set(columns)
    assert columns["lead_id"]["nullable"] is False
    with engine.begin() as connection:
        assert connection.execute(sa.text("SELECT COUNT(*) FROM calls")).scalar_one() == 0
    engine.dispose()
