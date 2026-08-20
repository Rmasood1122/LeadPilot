"""Alembic migration environment.

Reads the database URL from app.config.settings (i.e. the DATABASE_URL
environment variable) so migrations always target the same DB as the app.
Model metadata comes from app.db.base.Base; Chunk 2 adds app/db/models.py,
which is imported here so `alembic revision --autogenerate` can see it.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.db.base import Base

import app.db.models  # noqa: F401  (registers all tables on Base.metadata)

config = context.config

# app/db/migrate.py may hand us a DIFFERENT url than settings.database_url:
# migrations must run on Neon's DIRECT endpoint, because session-scoped
# pg_advisory_lock does not serialise through the PgBouncer POOLER. Measured
# against the live database on 2026-08-20 — pooled: a second migrator acquired
# a lock the first was holding; direct: correctly refused. Falls back to
# settings when nothing was passed, so every existing caller is unaffected.
_url_override = config.attributes.get("migration_url")
config.set_main_option("sqlalchemy.url", _url_override or settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=_url_override or settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
