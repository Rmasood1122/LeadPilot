"""Migration 0064 (Part 2) must add exactly the meeting_prep_briefs columns and
create exactly the two roleplay tables the models declare."""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m  # noqa: F401
from app.db.base import Base

MIGRATION = "0064_meeting_practice.py"
BRIEFS = "meeting_prep_briefs"
SESSIONS = "roleplay_sessions"
TURNS = "roleplay_turns"
ADDED = ["script_json", "script_edited_at", "script_edited_by_user_id",
         "practice_required"]
# `workspaces` and `client_workspaces` are here because `strategies` gained a
# foreign key to the latter in 0063 -- a prereq list that predates it builds a
# `strategies` table SQLite refuses to create.
_PREREQ = ["users", "workspaces", "client_workspaces", "products", "strategies",
           "lead_batches", "linkedin_accounts", "leads", "calendar_availability",
           "calendar_booking_pages", "calendar_bookings", "meetings",
           "meeting_prep_briefs"]


def _load(name):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    spec = importlib.util.spec_from_file_location(
        name[:-3], os.path.join(root, "alembic", "versions", name))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_prereqs(engine):
    """The pre-migration schema: no roleplay tables, and `meeting_prep_briefs`
    without its script columns or the foreign key one of them carries."""
    meta = sa.MetaData(naming_convention=Base.metadata.naming_convention)
    for table in Base.metadata.sorted_tables:
        table.to_metadata(meta)
    briefs = meta.tables[BRIEFS]
    for index in list(briefs.indexes):
        if any(col.name in ADDED for col in index.columns):
            briefs.indexes.remove(index)
    for fk in list(briefs.foreign_keys):
        if fk.parent.name in ADDED:
            briefs.foreign_keys.discard(fk)
    for constraint in list(briefs.constraints):
        if any(col.name in ADDED for col in getattr(constraint, "columns", [])):
            briefs.constraints.discard(constraint)
    for name in ADDED:
        briefs._columns.remove(briefs.c[name])
    meta.create_all(engine, tables=[meta.tables[t] for t in _PREREQ])


def _describe(inspector, table):
    return {
        "columns": {c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
                    for c in inspector.get_columns(table)},
        "indexes": {i["name"]: list(i["column_names"])
                    for i in inspector.get_indexes(table)},
        "uniques": {u["name"]: sorted(u["column_names"])
                    for u in inspector.get_unique_constraints(table)},
        "fks": {(tuple(f["constrained_columns"]), f["referred_table"])
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


def test_the_revision_follows_0063():
    module = _load(MIGRATION)
    assert module.revision == "0064_meeting_practice"
    assert module.down_revision == "0063_client_workspaces"


def test_the_session_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration, SESSIONS) == _describe(from_models, SESSIONS)


def test_the_turn_table_matches_the_model(from_models, from_migration):
    assert _describe(from_migration, TURNS) == _describe(from_models, TURNS)


def test_the_brief_columns_match_the_model(from_models, from_migration):
    added = {name: _describe(from_migration, BRIEFS)["columns"][name] for name in ADDED}
    expected = {name: _describe(from_models, BRIEFS)["columns"][name] for name in ADDED}
    assert added == expected


def test_a_brief_from_before_this_revision_has_no_script(from_migration):
    """NULL script_json is "never written", which is what ensure_script reads
    to decide whether it may seed one."""
    columns = {c["name"]: c for c in from_migration.get_columns(BRIEFS)}
    assert columns["script_json"]["nullable"] is True


def test_practice_is_not_required_by_default(from_migration):
    """Making every call require a rehearsal is how a checklist becomes
    something people click through without reading."""
    columns = {c["name"]: c for c in from_migration.get_columns(BRIEFS)}
    default = str(columns["practice_required"]["default"]).lower()
    assert columns["practice_required"]["nullable"] is False
    assert "false" in default or default == "0"


def test_two_lines_cannot_take_the_same_turn_number(from_migration):
    """What makes a duplicated submit a conflict rather than a duplicated
    line."""
    uniques = {u["name"]: sorted(u["column_names"])
               for u in from_migration.get_unique_constraints(TURNS)}
    assert uniques["roleplay_turn_order"] == ["session_id", "turn_no"]


def test_a_practice_history_outlives_the_prospect_it_was_practised_against(
        from_migration):
    """SET NULL on lead_id and brief_id: the history is about the SELLER."""
    rules = {tuple(f["constrained_columns"]): f["options"].get("ondelete")
             for f in from_migration.get_foreign_keys(SESSIONS)}
    assert rules[("lead_id",)] == "SET NULL"
    assert rules[("brief_id",)] == "SET NULL"
    # The user's own sessions go with the user.
    assert rules[("user_id",)] == "CASCADE"


def test_turns_go_with_their_session(from_migration):
    rules = {tuple(f["constrained_columns"]): f["options"].get("ondelete")
             for f in from_migration.get_foreign_keys(TURNS)}
    assert rules[("session_id",)] == "CASCADE"


def test_downgrade_round_trips(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'rt.db'}")
    _build_prereqs(engine)
    module = _load(MIGRATION)
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            module.downgrade()
    inspector = sa.inspect(engine)
    assert SESSIONS not in inspector.get_table_names()
    assert TURNS not in inspector.get_table_names()
    assert not set(ADDED) & {c["name"] for c in inspector.get_columns(BRIEFS)}
    engine.dispose()
