"""Migration 0088 (local business mode): four columns and one table, matching
the model; existing sequences become `prospects`; names fit PostgreSQL's
63-character limit; downgrade round-trips."""

from __future__ import annotations

import importlib.util
import os

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATION = "0088_local_business.py"
TABLE = "customer_imports"
_PREREQ = ["users", "products", "strategies", "sequences"]
_ADDED = {("products", "business_type"), ("products", "healthcare_locked_at"),
          ("strategies", "service_area_json"),
          ("strategies", "local_offer"), ("sequences", "audience")}


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
    """The schema as it was at 0087: every model table except the one 0088
    creates, with the four columns 0088 adds dropped again."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'lb.db'}")
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    meta.create_all(engine, tables=[t for t in meta.sorted_tables if t.name != TABLE])

    def drop_added():
        from alembic import op

        for table, column in sorted(_ADDED):
            op.drop_column(table, column)

    _run(engine, drop_added)
    return engine


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: list(i["column_names"]) for i in inspector.get_indexes(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"],
                 f["options"].get("ondelete"), f["name"])
                for f in inspector.get_foreign_keys(table)},
    }


def test_the_revision_follows_0087():
    module = _load()
    assert module.revision == "0088_local_business"
    assert module.down_revision == "0087_autopilot_launch"


def test_upgrade_matches_the_model(tmp_path):
    engine = _engine_before(tmp_path)
    with engine.begin() as connection:
        connection.execute(sa.text(
            "INSERT INTO sequences (id, strategy_id, channel, name, status, created_at, "
            "updated_at) VALUES ('s1', 'x', 'email', 'Old', 'active', CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)"))
    _run(engine, _load().upgrade)
    inspector = sa.inspect(engine)
    for table, column in _ADDED:
        got = {c["name"]: c for c in inspector.get_columns(table)}[column]
        model = Base.metadata.tables[table].c[column]
        assert bool(got["nullable"]) == bool(model.nullable), (table, column)
    with engine.begin() as connection:
        assert connection.execute(sa.text(
            "SELECT audience FROM sequences WHERE id = 's1'")).scalar_one() == "prospects"

    reference = sa.create_engine(f"sqlite:///{tmp_path / 'model.db'}")
    Base.metadata.create_all(reference)
    assert _describe(inspector, TABLE) == _describe(sa.inspect(reference), TABLE)
    engine.dispose()
    reference.dispose()


def test_constraint_names_fit_postgres():
    source = open(os.path.join(ROOT, "alembic", "versions", MIGRATION), encoding="utf-8").read()
    import re

    names = re.findall(r'name="([^"]+)"', source) + re.findall(r'"(ix_[a-z_]+)"', source)
    assert names and all(len(n) <= 63 for n in names), names
    for constraint in Base.metadata.tables[TABLE].constraints:
        assert constraint.name is None or len(constraint.name) <= 63
    assert "postgresql." not in source and "JSONB" not in source


def test_downgrade_round_trips(tmp_path):
    engine = _engine_before(tmp_path)
    module = _load()
    _run(engine, module.upgrade, module.downgrade)
    inspector = sa.inspect(engine)
    assert TABLE not in inspector.get_table_names()
    for table, column in _ADDED:
        assert column not in {c["name"] for c in inspector.get_columns(table)}
    engine.dispose()
