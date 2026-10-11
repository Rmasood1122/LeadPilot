"""Migration 0082: the notice table and the three added columns match the
models (same technique as tests/test_champion_tracker_migration.py), the
F04 default keeps the old behaviour for existing rows, and downgrade
round-trips."""

from __future__ import annotations

import importlib.util
import os
import uuid

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0082_annual_billing.py"
TABLE = "billing_renewal_notices"
_PREREQ = ["users", "billing_subscriptions", "reply_copilot_settings"]
BILLING_COLUMNS = ("trial_started_at", "trial_used", "renewal_consent_at",
                   "consent_disclosure_version", "consent_price_cents", "consent_interval",
                   "consent_checkout_session_id", "price_unit_amount_cents", "price_interval",
                   "price_currency", "support_note")


def _load(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(root, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_prereqs(engine):
    """The prerequisite tables as they were BEFORE 0081 (the added columns
    removed), so the migration's add_column calls are what is tested."""
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    added = {"billing_subscriptions": BILLING_COLUMNS,
             "reply_copilot_settings": ("answer_earlier_replies",)}
    for name, cols in added.items():
        table = meta.tables[name]
        for col in cols:
            table._columns.remove(table.c[col])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


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


@pytest.fixture()
def from_models(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    yield sa.inspect(engine)
    engine.dispose()


@pytest.fixture()
def migrated(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    _build_prereqs(engine)   # SQLite does not enforce FKs here: no users row needed
    yield engine
    engine.dispose()


def test_the_revision_follows_0080_champion_tracker():
    module = _load(MIGRATION)
    assert module.revision == "0082_annual_billing"
    assert module.down_revision == "0081_daily_send_approval"


def test_activation_script_targets_this_revision():
    from scripts import activate_with_keys as act

    # The script targets the chain's single head; this revision must be in
    # its history (later migrations move the head forward).
    from alembic.config import Config  # noqa: PLC0415
    from alembic.script import ScriptDirectory  # noqa: PLC0415

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    heads = script.get_heads()
    assert heads == [act.TARGET_REVISION]
    assert "0082_annual_billing" in {r.revision for r in script.walk_revisions("base", heads[0])}


def test_tables_match_the_models(tmp_path, from_models):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    _build_prereqs(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
    migrated = sa.inspect(engine)
    for table in (TABLE, "billing_subscriptions", "reply_copilot_settings"):
        assert _describe(migrated, table) == _describe(from_models, table), table
    engine.dispose()


def test_one_notice_per_subscription_kind_and_period(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'u.db'}")
    _build_prereqs(engine)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
    uniques = {u["name"]: sorted(u["column_names"])
               for u in sa.inspect(engine).get_unique_constraints(TABLE)}
    assert uniques["uq_billing_renewal_notice"] == ["kind", "period_key", "subscription_id"]
    rules = {(tuple(f["constrained_columns"]), f["referred_table"]): f["options"].get("ondelete")
             for f in sa.inspect(engine).get_foreign_keys(TABLE)}
    assert rules[(("user_id",), "users")] == "CASCADE"
    assert rules[(("subscription_id",), "billing_subscriptions")] == "CASCADE"
    engine.dispose()


def test_existing_copilot_rows_keep_answering_earlier_replies(migrated):
    """server_default TRUE: an account that existed before 0081 behaves
    exactly as it did."""
    with migrated.begin() as connection:
        user_id = uuid.uuid4().hex
        connection.execute(sa.text(
            "INSERT INTO reply_copilot_settings (id, user_id, auto_send_meeting_time) "
            "VALUES (:id, :u, 0)"), {"id": uuid.uuid4().hex, "u": user_id})
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
        value = connection.execute(sa.text(
            "SELECT answer_earlier_replies FROM reply_copilot_settings")).scalar_one()
    assert bool(value) is True


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    assert TABLE not in set(inspector.get_table_names())
    sub_cols = {c["name"] for c in inspector.get_columns("billing_subscriptions")}
    assert not set(BILLING_COLUMNS) & sub_cols
    assert "billing_model" in sub_cols
    rc_cols = {c["name"] for c in inspector.get_columns("reply_copilot_settings")}
    assert "answer_earlier_replies" not in rc_cols and "auto_send_meeting_time" in rc_cols
    engine.dispose()


def test_trial_used_is_backfilled_from_trial_ends_at(migrated):
    """An account that had a trial before 0081 must not get a second one."""
    with migrated.begin() as connection:
        for trial in ("2026-01-01 00:00:00", None):
            connection.execute(sa.text(
                "INSERT INTO billing_subscriptions (id, user_id, billing_model, tier, status, "
                "cancel_at_period_end, is_stub, trial_ends_at) VALUES (:id, :u, 'monthly', "
                "'starter', 'canceled', 0, 0, :t)"),
                {"id": uuid.uuid4().hex, "u": uuid.uuid4().hex, "t": trial})
        with Operations.context(MigrationContext.configure(connection)):
            _load(MIGRATION).upgrade()
        rows = connection.execute(sa.text(
            "SELECT trial_ends_at IS NOT NULL, trial_used FROM billing_subscriptions")).all()
    assert sorted((bool(a), bool(b)) for a, b in rows) == [(False, False), (True, True)]
