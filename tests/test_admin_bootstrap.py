"""ADMIN_EMAIL bootstrap (app/core/admin_bootstrap.py).

ADMIN_EMAIL was declared in config and read by nothing, so a freshly deployed
database had no admin and no way to create one over HTTP — every /admin route
and /playbook/aggregate was unreachable. These tests pin the wiring and the
two properties that make it safe to run on every single startup: it never
creates duplicates, and it never downgrades a different admin.
"""
from __future__ import annotations

import pytest

from app.core.admin_bootstrap import bootstrap_admin, ensure_admin_from_env
from app.db import models as m


@pytest.fixture()
def make_user(db_session):
    def _make(email: str, *, is_admin: bool = False) -> m.User:
        user = m.User(email=email, is_admin=is_admin)
        db_session.add(user)
        db_session.commit()
        return user
    return _make


class TestPromotion:
    def test_configured_user_becomes_admin(self, db_session, make_user):
        """(a) ADMIN_EMAIL set → that user ends up with admin rights."""
        user = make_user("boss@corp.test")
        assert user.is_admin is False

        assert ensure_admin_from_env(db_session, "boss@corp.test") is True

        db_session.refresh(user)
        assert user.is_admin is True

    def test_admin_rights_actually_pass_require_admin(self, db_session, make_user):
        """The promotion has to satisfy the real gate, not just set a column."""
        from fastapi import HTTPException

        from app.api.deps import require_admin

        user = make_user("gate@corp.test")
        with pytest.raises(HTTPException) as exc_info:
            require_admin(current_user=user)
        assert exc_info.value.status_code in (401, 403)

        ensure_admin_from_env(db_session, "gate@corp.test")
        db_session.refresh(user)
        assert require_admin(current_user=user) is user

    def test_email_match_is_case_insensitive(self, db_session, make_user):
        user = make_user("mixed@corp.test")
        assert ensure_admin_from_env(db_session, "  MiXeD@Corp.TEST  ") is True
        db_session.refresh(user)
        assert user.is_admin is True


class TestIdempotenceAndSafety:
    def test_running_twice_changes_nothing_the_second_time(self, db_session,
                                                           make_user):
        make_user("repeat@corp.test")
        assert ensure_admin_from_env(db_session, "repeat@corp.test") is True
        assert ensure_admin_from_env(db_session, "repeat@corp.test") is False

    def test_no_duplicate_users_are_created(self, db_session, make_user):
        make_user("solo@corp.test")
        for _ in range(3):
            ensure_admin_from_env(db_session, "solo@corp.test")
        assert db_session.query(m.User).filter(
            m.User.email == "solo@corp.test").count() == 1

    def test_never_downgrades_a_different_admin(self, db_session, make_user):
        """An admin promoted by the CLI must survive a different ADMIN_EMAIL."""
        cli_admin = make_user("cli@corp.test", is_admin=True)
        env_admin = make_user("env@corp.test")

        ensure_admin_from_env(db_session, "env@corp.test")

        db_session.refresh(cli_admin)
        db_session.refresh(env_admin)
        assert cli_admin.is_admin is True, "the other admin was downgraded"
        assert env_admin.is_admin is True

    def test_missing_user_is_reported_not_invented(self, db_session, caplog):
        """No password-reset flow exists, so an account created here could
        never be logged into. It reports instead — loudly."""
        import logging

        with caplog.at_level(logging.ERROR):
            assert ensure_admin_from_env(db_session, "ghost@corp.test") is False

        assert db_session.query(m.User).filter(
            m.User.email == "ghost@corp.test").count() == 0
        assert "app.cli.create_admin" in caplog.text, (
            "the operator must be told exactly how to fix it"
        )


class TestUnsetAdminEmail:
    """(b) an unset ADMIN_EMAIL must not break startup on a fresh DB."""

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_unset_is_a_silent_no_op(self, db_session, value):
        assert ensure_admin_from_env(db_session, value) is False
        assert db_session.query(m.User).count() == 0

    def test_bootstrap_never_raises_without_config(self, monkeypatch):
        from app.core import config as core_config

        monkeypatch.setattr(core_config.settings, "ADMIN_EMAIL", None,
                            raising=False)
        assert bootstrap_admin() is False

    def test_bootstrap_never_raises_when_the_database_is_unreachable(
            self, monkeypatch):
        """Startup must survive a database that is down or unmigrated."""
        from app.core import config as core_config

        monkeypatch.setattr(core_config.settings, "ADMIN_EMAIL",
                            "boom@corp.test", raising=False)

        def _explode():
            raise RuntimeError("database is not reachable")

        monkeypatch.setattr("app.db.base.SessionLocal", _explode)
        assert bootstrap_admin() is False

    def test_bootstrap_actually_runs_on_application_startup(self, db_session,
                                                             make_user,
                                                             monkeypatch):
        """The wiring itself — a function nothing calls is what got us here.

        Drives the REAL lifespan by entering TestClient as a context manager,
        rather than asserting a handler is merely registered.
        """
        from fastapi.testclient import TestClient

        from app.core import config as core_config
        import app.main as main

        make_user("lifespan@corp.test")
        monkeypatch.setattr(core_config.settings, "ADMIN_EMAIL",
                            "lifespan@corp.test", raising=False)
        # The bootstrap opens — and closes — its own session from SessionLocal,
        # so hand it this one and re-query afterwards rather than holding an
        # instance across the close().
        monkeypatch.setattr("app.db.base.SessionLocal", lambda: db_session)

        with TestClient(main.app):
            pass

        promoted = db_session.query(m.User).filter(
            m.User.email == "lifespan@corp.test").one()
        assert promoted.is_admin is True, (
            "application startup did not run the ADMIN_EMAIL bootstrap"
        )
