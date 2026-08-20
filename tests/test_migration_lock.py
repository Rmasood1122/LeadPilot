"""Migrations must be serialised, and must never be run bare in a start command.

`docker-compose.prod.yml` used to run `alembic upgrade head` inline in the api
service's command. Safe at one replica; a race at two. Measured 2026-08-20 with
four migrators started together against a fresh database: WITHOUT the advisory
lock 3 of 4 exited non-zero with an IntegrityError on the alembic_version
insert (a container crash-loop on deploy); WITH the lock all four exited 0 and
the schema landed at head exactly once.

The concurrency behaviour itself needs a real PostgreSQL server and is verified
by the scripted four-process run recorded in DEPLOY_RAILWAY.md. What is pinned
here is the wiring that makes that fix reachable: the lock identifier, the
blocking semantics, and the deployment configs that must call the locked entry
point rather than alembic directly.
"""

import json
import os
import re

import pytest

from app.db import migrate

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(name: str) -> str:
    with open(os.path.join(_ROOT, name), encoding="utf-8") as handle:
        return handle.read()


class TestLockIdentifier:
    def test_lock_id_is_a_valid_postgres_bigint(self):
        """pg_advisory_lock takes a signed 64-bit key; overflow is an error."""
        assert -(2 ** 63) <= migrate.MIGRATION_ADVISORY_LOCK_ID < 2 ** 63

    def test_lock_id_is_stable(self):
        """Changing this silently disables mutual exclusion between versions:
        an old and a new container would take different locks and race."""
        assert migrate.MIGRATION_ADVISORY_LOCK_ID == 8_274_301_995_517_460_021 - (1 << 63)


class TestBlockingSemantics:
    def test_uses_blocking_lock_not_try_lock(self):
        """`pg_try_advisory_lock` would let a replica give up and boot against
        the un-migrated schema — the exact failure the lock exists to prevent."""
        source = _read(os.path.join("app", "db", "migrate.py"))
        assert "pg_advisory_lock(" in source
        # Match the CALL, not prose: the module docstring legitimately names
        # pg_try_advisory_lock while explaining why it is the wrong choice.
        assert "pg_try_advisory_lock(" not in source

    def test_lock_is_released_even_when_the_upgrade_raises(self):
        """A failed migration must not leave the lock held for the next deploy."""
        source = _read(os.path.join("app", "db", "migrate.py"))
        # The unlock must sit in a finally block attached to the upgrade call.
        # `_run_alembic_upgrade` takes the migration url since 2026-08-20 (it
        # must migrate the same endpoint the lock was taken on), so the call
        # may carry an argument — the `finally` is what this guards.
        assert re.search(
            r"try:\s*\n\s*_run_alembic_upgrade\([^)]*\)\s*\n\s*finally:", source
        ), "the advisory unlock is not in a finally around the upgrade"
        assert "pg_advisory_unlock" in source


class TestNonPostgresPath:
    def test_sqlite_skips_the_lock(self, monkeypatch):
        """SQLite has no advisory locks and no concurrent-start problem; the
        unit suite must not need a PostgreSQL server to migrate."""
        called = {}
        monkeypatch.setattr(migrate, "_run_alembic_upgrade",
                            lambda url=None: called.setdefault("ran", True))

        status = migrate.run_migrations("sqlite:///:memory:")

        assert called.get("ran") is True
        assert "no lock" in status

    @pytest.mark.parametrize("url,expected", [
        ("postgresql://u:p@h/db", True),
        ("postgresql+psycopg2://u:p@h/db", True),
        ("sqlite:///:memory:", False),
        ("sqlite://", False),
    ])
    def test_postgres_detection(self, url, expected):
        assert migrate._is_postgres(url) is expected


class TestDeploymentConfigsUseTheLockedEntryPoint:
    def test_compose_api_does_not_run_bare_alembic(self):
        """The original defect, pinned so it cannot come back."""
        compose = _read("docker-compose.prod.yml")
        command_lines = [
            line for line in compose.splitlines()
            if "alembic upgrade head" in line and not line.strip().startswith("#")
        ]
        assert not command_lines, (
            f"docker-compose.prod.yml runs alembic directly instead of "
            f"`python -m app.db.migrate`: {command_lines}"
        )
        assert "python -m app.db.migrate" in compose

    def test_railway_api_runs_migrations_as_a_pre_deploy_command(self):
        config = json.loads(_read(os.path.join("railway", "api.json")))
        pre_deploy = config["deploy"]["preDeployCommand"]
        assert any("app.db.migrate" in c for c in pre_deploy), pre_deploy

    def test_no_railway_start_command_migrates(self):
        """Migrating in a startCommand reintroduces the per-replica race, and
        doing it in a worker's command would race the API's pre-deploy too."""
        import glob

        for path in glob.glob(os.path.join(_ROOT, "railway", "*.json")):
            config = json.loads(_read(os.path.join("railway", os.path.basename(path))))
            start = config["deploy"]["startCommand"]
            assert "alembic" not in start, f"{os.path.basename(path)}: {start}"
            assert "app.db.migrate" not in start, f"{os.path.basename(path)}: {start}"

    def test_railway_api_healthcheck_points_at_the_real_endpoint(self):
        config = json.loads(_read(os.path.join("railway", "api.json")))
        assert config["deploy"]["healthcheckPath"] == "/health"
