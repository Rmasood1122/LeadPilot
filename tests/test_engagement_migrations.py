"""Migrations 0020–0022 must produce exactly the schema the models declare.

WHY THIS TEST EXISTS
Identical reasoning to tests/test_crm_migration.py, which this is modelled on.
The suite builds its database with `Base.metadata.create_all()` (SQLite,
in-memory); production builds it by running migrations and never touches
create_all. The two descriptions of the schema are therefore exercised by
completely disjoint code paths, so a column added to a model and forgotten in
the migration passes every other test in this repository while being absent
from the deployed database — surfacing at runtime, in production, as "no such
column" on a query nobody changed.

It cannot run the whole chain (0008_m8c2 adds a foreign key by ALTER, which
SQLite does not support outside batch mode), so the tables these three
migrations depend on are created from metadata and only 0020–0022 are executed
on top. That is precisely the comparison that matters.

THE sequence_steps CASE IS THE INTERESTING ONE. 0020 ALTERs an existing table,
so the prerequisite has to be built WITHOUT the two columns the migration adds
— otherwise the test would be comparing a table to itself and would pass even
if upgrade() were empty.
"""

from __future__ import annotations

import importlib.util
import os

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.db import models as m
from app.db.base import Base

# The tables these migrations create. A literal rather than something derived
# from the metadata, so that adding a table to the models without adding it to
# a migration fails HERE instead of silently shrinking the comparison.
ENGAGEMENT_TABLES = [
    "calendar_availability",
    "calendar_booking_pages",
    "calendar_bookings",
    "meetings",
    "meeting_participants",
]

# Everything the three migrations' foreign keys point at, plus sequence_steps,
# which 0020 alters.
_PREREQ_TABLES = [
    "users", "products", "strategies", "lead_batches", "leads",
    "sequences", "sequence_steps", "whatsapp_templates",
]

# The columns 0020 ADDS. Removed from the prerequisite build so the migration
# has real work to do. See the module docstring.
_ADDED_TO_SEQUENCE_STEPS = ["followup_enabled", "followup_delay_hours"]

MIGRATIONS = ["0020_followup_delay.py", "0021_calendar.py", "0022_meetings.py"]


def _load(name: str):
    """Import a revision file by path — alembic/versions is not a package."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "alembic", "versions", name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _describe(inspector, table: str) -> dict:
    """The comparable shape of one table.

    Column types are compared as their SQLite-rendered string, because that is
    what both sides actually become on this dialect; comparing SQLAlchemy type
    objects would report VARCHAR(32) != String(32) and be useless.
    """
    return {
        "columns": {
            c["name"]: {"type": str(c["type"]), "nullable": bool(c["nullable"])}
            for c in inspector.get_columns(table)
        },
        "indexes": {
            i["name"]: {"columns": list(i["column_names"]),
                        "unique": bool(i["unique"])}
            for i in inspector.get_indexes(table)
        },
        "uniques": {
            u["name"]: sorted(u["column_names"])
            for u in inspector.get_unique_constraints(table)
        },
        "fks": {
            (tuple(f["constrained_columns"]), f["referred_table"],
             tuple(f["referred_columns"]))
            for f in inspector.get_foreign_keys(table)
        },
    }


@pytest.fixture()
def from_models(tmp_path):
    """Schema as create_all() builds it — what the test suite runs on."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'models.db'}")
    Base.metadata.create_all(engine)
    yield sa.inspect(engine)
    engine.dispose()


@pytest.fixture()
def from_migration(tmp_path):
    """Schema as 0020–0022 build it — what production runs on."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'migration.db'}")

    # Build sequence_steps WITHOUT the columns 0020 adds, so the ALTER is real.
    steps = Base.metadata.tables["sequence_steps"]
    removed = [steps.c[name] for name in _ADDED_TO_SEQUENCE_STEPS]
    for column in removed:
        steps._columns.remove(column)
    try:
        Base.metadata.create_all(
            engine, tables=[Base.metadata.tables[t] for t in _PREREQ_TABLES]
        )
    finally:
        # Restore the metadata whatever happens: it is module-level state
        # shared with every other test in the process, and leaving two columns
        # missing from it would break them in ways that point nowhere near here.
        for column in removed:
            steps.append_column(column)

    for name in MIGRATIONS:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                _load(name).upgrade()

    yield sa.inspect(engine)
    engine.dispose()


class TestMigrationsMatchModels:
    def test_every_table_is_created(self, from_migration):
        created = set(from_migration.get_table_names())
        missing = set(ENGAGEMENT_TABLES) - created
        assert not missing, f"migrations did not create: {sorted(missing)}"

    def test_models_declare_every_table(self):
        """The other direction: a table in a migration but not in the models."""
        declared = {
            t for t in Base.metadata.tables
            if t.startswith("calendar_") or t.startswith("meeting")
        }
        assert declared == set(ENGAGEMENT_TABLES)

    @pytest.mark.parametrize("table", ENGAGEMENT_TABLES + ["sequence_steps"])
    def test_columns_match(self, table, from_models, from_migration):
        assert (_describe(from_migration, table)["columns"]
                == _describe(from_models, table)["columns"])

    @pytest.mark.parametrize("table", ENGAGEMENT_TABLES)
    def test_indexes_match(self, table, from_models, from_migration):
        """A missing index is invisible until the table has real volume, and
        then it is a slow-query incident rather than an error."""
        assert (_describe(from_migration, table)["indexes"]
                == _describe(from_models, table)["indexes"])

    @pytest.mark.parametrize("table", ENGAGEMENT_TABLES)
    def test_unique_constraints_match(self, table, from_models, from_migration):
        """calendar_booking_live_slot is the double-booking guard. If the
        migration ships without it, production accepts two bookings for one
        slot and every test here still passes."""
        assert (_describe(from_migration, table)["uniques"]
                == _describe(from_models, table)["uniques"])

    @pytest.mark.parametrize("table", ENGAGEMENT_TABLES)
    def test_foreign_keys_match(self, table, from_models, from_migration):
        assert (_describe(from_migration, table)["fks"]
                == _describe(from_models, table)["fks"])

    def test_0020_actually_adds_the_followup_columns(self, from_migration):
        """Guards the fixture as much as the migration: if the prerequisite
        build stopped removing them, this would pass vacuously — so it also
        asserts they are NOT NULL, which only the migration can arrange."""
        columns = {c["name"]: c
                   for c in from_migration.get_columns("sequence_steps")}
        for name in _ADDED_TO_SEQUENCE_STEPS:
            assert name in columns, f"0020 did not add {name}"
            assert not columns[name]["nullable"], (
                f"{name} must be NOT NULL — a NULL delay makes the follow-up "
                f"sweep silently skip every step that existed before 0020"
            )


class TestMigrationsAreReversible:
    def test_downgrade_drops_every_new_table(self, tmp_path):
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'roundtrip.db'}")
        Base.metadata.create_all(
            engine, tables=[Base.metadata.tables[t] for t in _PREREQ_TABLES]
        )
        modules = [_load(name) for name in MIGRATIONS]
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                # 0020's upgrade would collide with the columns create_all
                # already made, so only the two table-creating migrations are
                # round-tripped here. 0020's own reversibility is a
                # drop_column pair with nothing to get wrong.
                for module in modules[1:]:
                    module.upgrade()
                for module in reversed(modules[1:]):
                    module.downgrade()
        remaining = set(sa.inspect(engine).get_table_names())
        engine.dispose()
        left = remaining & set(ENGAGEMENT_TABLES)
        assert not left, f"downgrade left tables behind: {sorted(left)}"


class TestRevisionChain:
    def test_the_chain_is_linear_and_in_order(self):
        chain = {_load(name).revision: _load(name).down_revision
                 for name in MIGRATIONS}
        assert chain["0020_followup_delay"] == "0019_m9_crm"
        assert chain["0021_calendar"] == "0020_followup_delay"
        assert chain["0022_meetings"] == "0021_calendar"

    def test_no_migration_touches_an_existing_table_destructively(self):
        """Rule 2 of the brief, pinned. 0020 legitimately ALTERs
        sequence_steps to ADD two columns; nothing may drop or alter one."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in MIGRATIONS:
            path = os.path.join(root, "alembic", "versions", name)
            with open(path, encoding="utf-8") as handle:
                upgrade = handle.read().split("def downgrade")[0]
            assert "op.drop_column(" not in upgrade, f"{name} drops a column"
            assert "op.drop_table(" not in upgrade, f"{name} drops a table"
            assert "op.alter_column(" not in upgrade, (
                f"{name} alters an existing column"
            )

    def test_no_engagement_migration_touches_outcomes_or_leads(self):
        """The learning loop reads `outcomes`, and the sourcing chain, the
        sequence engine and the published SDK all load `leads`. Neither gains
        a column for this feature."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in MIGRATIONS:
            path = os.path.join(root, "alembic", "versions", name)
            with open(path, encoding="utf-8") as handle:
                source = handle.read()
            for table in ("outcomes", "leads", "strategies", "messages"):
                for verb in ("add_column", "drop_column", "alter_column"):
                    assert f'op.{verb}("{table}"' not in source, (
                        f"{name} calls op.{verb} on {table}"
                    )


class TestModelInvariants:
    def test_booking_status_and_meeting_enums_are_varchar_backed(self):
        """native_enum=False everywhere in this schema: adding a value later
        is a data-free change, and SQLite behaves like PostgreSQL."""
        for column in (m.CalendarBooking.__table__.c.status,
                       m.Meeting.__table__.c.status,
                       m.Meeting.__table__.c.platform,
                       m.MeetingParticipant.__table__.c.role):
            assert isinstance(column.type, sa.Enum)
            assert column.type.native_enum is False

    def test_meeting_booking_and_lead_links_are_nullable(self):
        """A manually created meeting has no booking, and a meeting with an
        unmatched invitee has no lead. NOT NULL on either would make both
        impossible — see the 0022 docstring."""
        assert m.Meeting.__table__.c.booking_id.nullable
        assert m.Meeting.__table__.c.lead_id.nullable
