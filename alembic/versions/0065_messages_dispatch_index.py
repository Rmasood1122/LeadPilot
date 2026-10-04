"""Index messages(status, scheduled_at) for the dispatcher's due-message scan.

F-DB-03. `leadpilot.outreach.dispatch` runs on every beat tick and selects
    WHERE status = 'scheduled' AND scheduled_at <= now ORDER BY scheduled_at
The table only had indexes on lead_id, origin and sequence_id, so each tick was
a sequential scan of every message ever written.

PostgreSQL: built with CREATE INDEX CONCURRENTLY so a live `messages` table is
not write-locked while it builds. CONCURRENTLY cannot run inside a transaction,
so it runs in Alembic's autocommit_block(). IF NOT EXISTS makes a re-run (for
example after an interrupted CONCURRENTLY build, which leaves an INVALID index
that must be dropped by hand) a no-op rather than an error.
Other dialects (SQLite in the offline suite): a plain, transactional index.

Revision ID: 0065_messages_dispatch_index
Revises: 0064_meeting_practice
"""

from alembic import op

revision = "0065_messages_dispatch_index"
down_revision = "0064_meeting_practice"
branch_labels = None
depends_on = None

INDEX = "ix_messages_status_scheduled_at"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX} "
                "ON messages (status, scheduled_at)"
            )
    else:
        op.create_index(INDEX, "messages", ["status", "scheduled_at"],
                        if_not_exists=True)


def downgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX}")
    else:
        op.drop_index(INDEX, table_name="messages", if_exists=True)
