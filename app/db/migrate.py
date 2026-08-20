"""Run Alembic migrations exactly once, even if several processes start together.

WHY THIS EXISTS
---------------
`docker-compose.prod.yml` used to run migrations inline in the api service:

    sh -c "alembic upgrade head && uvicorn app.main:app ... --workers 2"

That is safe at ONE replica and races the moment there are two. Two replicas
starting together both call `alembic upgrade head` against the same database;
both read the same current revision, and both try to apply the same DDL. The
failure is ugly and version-dependent — a duplicate column/index/constraint
error, a half-applied revision, or a deadlock between the two migration
transactions — and it happens exactly when you are scaling up under load.

THE FIX
-------
A PostgreSQL advisory lock around the upgrade. The first process in takes the
lock and migrates; any other process BLOCKS until it is released, then runs its
own upgrade and finds there is nothing left to do. Serialised, not skipped —
so a replica never starts against a half-migrated schema.

`pg_advisory_lock` is deliberately the blocking form rather than
`pg_try_advisory_lock`: a replica that cannot get the lock must wait for the
migration to finish, not race ahead and boot against the old schema.

The lock is session-scoped and released explicitly in a finally block; even if
the process is killed, PostgreSQL drops it when the connection closes, so a
crashed migrator cannot wedge every future deploy.

RAILWAY
-------
Railway's native mechanism is a pre-deploy command, which runs in a separate
container before the new version starts (see railway.json). That is the
recommended shape and it is configured. This lock is defence in depth: Railway's
docs do not state whether the pre-deploy command runs once per deployment or
once per replica, and the lock makes the answer not matter. It also protects
the self-hosted docker-compose path, which has no pre-deploy concept at all.

USAGE
-----
    python -m app.db.migrate          # what the pre-deploy command runs
"""

from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

# Stable, arbitrary 64-bit key. Any process migrating THIS database must use
# the same number; changing it silently disables the mutual exclusion.
MIGRATION_ADVISORY_LOCK_ID = 8_274_301_995_517_460_021 - (1 << 63)

_LOCK_WAIT_STATEMENT_TIMEOUT_MS = 0  # 0 = wait indefinitely for the lock


def _database_url() -> str:
    from app.config import settings

    return os.getenv("DATABASE_URL") or settings.database_url


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql") or url.startswith("postgres://")


def _run_alembic_upgrade() -> None:
    """Upgrade to head using Alembic's own API.

    alembic/env.py overwrites sqlalchemy.url from settings.database_url, so the
    config file's value is irrelevant here — DATABASE_URL governs.
    """
    from alembic import command
    from alembic.config import Config

    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config = Config(os.path.join(root, "alembic.ini"))
    command.upgrade(config, "head")


def run_migrations(url: str | None = None) -> str:
    """Apply migrations under an advisory lock. Returns a short status string.

    Non-PostgreSQL databases (SQLite in the unit-test suite) have no advisory
    locks and no concurrent-start problem, so they migrate directly.
    """
    url = url or _database_url()

    if not _is_postgres(url):
        logger.info("migrate: non-postgres url, running without advisory lock")
        _run_alembic_upgrade()
        return "migrated (no lock: not postgres)"

    engine = create_engine(url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    connection = engine.connect()
    try:
        if _LOCK_WAIT_STATEMENT_TIMEOUT_MS:
            connection.execute(
                text(f"SET statement_timeout = {_LOCK_WAIT_STATEMENT_TIMEOUT_MS}")
            )
        logger.info("migrate: acquiring advisory lock %s", MIGRATION_ADVISORY_LOCK_ID)
        connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
        )
        logger.info("migrate: lock acquired, upgrading to head")
        try:
            _run_alembic_upgrade()
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
            )
            logger.info("migrate: advisory lock released")
        return "migrated (advisory lock held)"
    finally:
        connection.close()
        engine.dispose()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    try:
        status = run_migrations()
    except Exception:
        logger.exception("migrate: FAILED")
        return 1
    logger.info("migrate: %s", status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
