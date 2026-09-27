"""Run ROOT test modules against local PostgreSQL instead of SQLite.

WHY
    The root suite (tests/*.py) runs on in-memory SQLite, which cannot show
    Postgres-only behaviour: UUID binding in raw SQL, IN subqueries against
    uuid columns, JSONB, FOR UPDATE. The fixtures in tests/integration/
    conftest.py are real Postgres, but they serve a different fixture library
    (api_client, factories), so root modules cannot use them. This plugin
    reruns a root module unchanged, on Postgres.

HOW IT WORKS
    tests/conftest.py's db_session builds
        create_engine("sqlite://", ..., poolclass=StaticPool)
    Loaded with `-p`, this module is imported BEFORE that conftest, so it
    replaces sqlalchemy.create_engine; that one call (and only calls made from
    tests/conftest.py) instead returns an engine on a fresh copy of an
    Alembic-migrated database:

      session start  DROP/CREATE lp_root_template, `alembic upgrade head`
                     into it (subprocess, DATABASE_URL overridden)
      every test     DROP/CREATE lp_root_run TEMPLATE lp_root_template
      session end    both databases dropped

    Each test therefore sees the real migrated schema (Base.metadata
    .create_all then adds nothing, or only model-only tables) and nothing a
    previous test wrote -- including a test that DROPs a table.

    Scope: the root db_session and everything that uses it (client, the
    get_db override). Code that opens its own session from SessionLocal is
    still bound to SQLite, exactly as in a normal root run.

RUN IT
    Local Postgres only. Start the compose db service -- NOT worker/beat, which
    can reach real APIs with keys from .env:

        docker compose up -d db

    then, from the repo root:

        python -m pytest -p tests.integration.pg_root_suite \\
            tests/test_admin_playbook_scores.py tests/test_playbook_scores.py

    PG_ROOT_SUITE_ADMIN_URL overrides the maintenance-database URL (default:
    the compose db on localhost:5433). Any host other than localhost /
    127.0.0.1 is refused, so .env's production database cannot be reached
    through this plugin.

    To tell that it really ran on Postgres: `-p` loading prints
    "pg_root_suite: ..." at session start, and a test can check
    `db_session.bind.dialect.name == "postgresql"`.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool, StaticPool

ADMIN_URL = make_url(os.getenv(
    "PG_ROOT_SUITE_ADMIN_URL",
    "postgresql+psycopg2://leadpilot:leadpilot@localhost:5433/postgres",
))
if ADMIN_URL.host not in ("localhost", "127.0.0.1"):
    raise RuntimeError(
        f"pg_root_suite refuses non-local PostgreSQL host {ADMIN_URL.host!r}"
    )

TEMPLATE_DB = "lp_root_template"
RUN_DB = "lp_root_run"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOT_CONFTEST = str(_REPO_ROOT / "tests" / "conftest.py")

_real_create_engine = sqlalchemy.create_engine


def _admin_exec(*statements: str) -> None:
    admin = _real_create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT",
                                poolclass=NullPool)
    try:
        with admin.connect() as conn:
            for stmt in statements:
                conn.exec_driver_sql(stmt)
    finally:
        admin.dispose()


def _build_template() -> None:
    _admin_exec(f"DROP DATABASE IF EXISTS {RUN_DB} WITH (FORCE)",
                f"DROP DATABASE IF EXISTS {TEMPLATE_DB} WITH (FORCE)",
                f"CREATE DATABASE {TEMPLATE_DB}")
    # A subprocess, for the reason given in tests/integration/conftest.py:
    # alembic/env.py reads settings.database_url, which in this process was
    # frozen to the root conftest's "sqlite://".
    template_url = ADMIN_URL.set(database=TEMPLATE_DB)
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(_REPO_ROOT),
        env={**os.environ,
             "DATABASE_URL": template_url.render_as_string(hide_password=False)},
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("\n".join([
            f"alembic upgrade head failed against {template_url}",
            "--- stdout ---", proc.stdout, "--- stderr ---", proc.stderr,
        ]))


def _fresh_run_engine():
    _admin_exec(f"DROP DATABASE IF EXISTS {RUN_DB} WITH (FORCE)",
                f"CREATE DATABASE {RUN_DB} TEMPLATE {TEMPLATE_DB}")
    return _real_create_engine(ADMIN_URL.set(database=RUN_DB), poolclass=NullPool)


def _create_engine(url, *args, **kwargs):
    caller = sys._getframe(1).f_code.co_filename
    if (str(url) == "sqlite://" and kwargs.get("poolclass") is StaticPool
            and os.path.normcase(caller) == os.path.normcase(_ROOT_CONFTEST)):
        return _fresh_run_engine()
    return _real_create_engine(url, *args, **kwargs)


sqlalchemy.create_engine = _create_engine


def pytest_configure(config):
    _build_template()
    print(f"pg_root_suite: root db_session -> {ADMIN_URL.host}:{ADMIN_URL.port}"
          f"/{RUN_DB} (template {TEMPLATE_DB}, alembic head)")


def pytest_unconfigure(config):
    _admin_exec(f"DROP DATABASE IF EXISTS {RUN_DB} WITH (FORCE)",
                f"DROP DATABASE IF EXISTS {TEMPLATE_DB} WITH (FORCE)")
