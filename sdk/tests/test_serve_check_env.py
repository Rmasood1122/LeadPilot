"""
Tests for `clienthunter serve --check-env` environment validation.
"""
from __future__ import annotations

import os
import pytest
from typer.testing import CliRunner
from clienthunter.cli.serve import app, check_env


runner = CliRunner()


# ---------------------------------------------------------------------------
# check_env() unit tests
# ---------------------------------------------------------------------------

class TestCheckEnv:
    def test_missing_secret_key_fails(self, monkeypatch):
        """Missing SECRET_KEY must report failure."""
        monkeypatch.delenv("SECRET_KEY", raising=False)
        all_ok, results = check_env()
        assert not all_ok
        sk = next(r for r in results if r["name"] == "SECRET_KEY")
        assert not sk["ok"]
        assert sk["required"] is True

    def test_short_secret_key_fails(self, monkeypatch):
        """SECRET_KEY shorter than 32 chars must report failure."""
        monkeypatch.setenv("SECRET_KEY", "short")
        all_ok, results = check_env()
        assert not all_ok
        sk = next(r for r in results if r["name"] == "SECRET_KEY")
        assert not sk["ok"]

    def test_valid_secret_key_passes(self, monkeypatch):
        """SECRET_KEY with 64 chars must pass."""
        monkeypatch.setenv("SECRET_KEY", "a" * 64)
        _, results = check_env()
        sk = next(r for r in results if r["name"] == "SECRET_KEY")
        assert sk["ok"]

    def test_missing_anthropic_key_fails(self, monkeypatch):
        """Missing ANTHROPIC_API_KEY must fail."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        all_ok, results = check_env()
        assert not all_ok
        ak = next(r for r in results if r["name"] == "ANTHROPIC_API_KEY")
        assert not ak["ok"]

    def test_anthropic_key_wrong_prefix_fails(self, monkeypatch):
        """ANTHROPIC_API_KEY not starting with 'sk-ant-' must fail."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "wrong-prefix-key")
        _, results = check_env()
        ak = next(r for r in results if r["name"] == "ANTHROPIC_API_KEY")
        assert not ak["ok"]
        assert "sk-ant-" in ak["detail"]

    def test_valid_anthropic_key_passes(self, monkeypatch):
        """Valid ANTHROPIC_API_KEY must pass."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-valid-key-here")
        _, results = check_env()
        ak = next(r for r in results if r["name"] == "ANTHROPIC_API_KEY")
        assert ak["ok"]

    def test_all_required_set_returns_all_ok(self, monkeypatch):
        """When all required vars are valid, all_ok must be True."""
        monkeypatch.setenv("SECRET_KEY", "a" * 64)
        monkeypatch.setenv("ENCRYPTION_KEY", "b" * 44)
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test-key")
        all_ok, _ = check_env()
        assert all_ok

    def test_optional_vars_do_not_cause_all_ok_false(self, monkeypatch):
        """Missing optional vars (Apollo, Hunter, etc.) must NOT make all_ok False."""
        monkeypatch.setenv("SECRET_KEY", "a" * 64)
        monkeypatch.setenv("ENCRYPTION_KEY", "b" * 44)
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test-key")
        monkeypatch.delenv("APOLLO_API_KEY", raising=False)
        monkeypatch.delenv("HUNTER_API_KEY", raising=False)
        all_ok, results = check_env()
        assert all_ok  # required vars are set → all_ok

        # Optional vars should show warning but not failure
        apollo = next(r for r in results if r["name"] == "APOLLO_API_KEY")
        assert not apollo["required"]

    def test_short_encryption_key_fails(self, monkeypatch):
        """ENCRYPTION_KEY shorter than 44 chars must fail."""
        monkeypatch.setenv("ENCRYPTION_KEY", "abc")
        _, results = check_env()
        ek = next(r for r in results if r["name"] == "ENCRYPTION_KEY")
        assert not ek["ok"]

    def test_database_url_wrong_prefix_fails(self, monkeypatch):
        """DATABASE_URL not starting with postgresql:// must fail."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///local.db")
        _, results = check_env()
        db = next(r for r in results if r["name"] == "DATABASE_URL")
        assert not db["ok"]
        assert "postgresql://" in db["detail"]


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------

class TestServeCLI:
    def test_check_env_exits_1_on_missing_vars(self, monkeypatch):
        """--check-env exits with code 1 when required vars are missing."""
        # Remove a required var
        monkeypatch.delenv("SECRET_KEY", raising=False)
        result = runner.invoke(app, ["--check-env"])
        assert result.exit_code == 1

    def test_check_env_exits_0_when_all_set(self, monkeypatch):
        """--check-env exits with code 0 when all required vars are valid."""
        monkeypatch.setenv("SECRET_KEY", "a" * 64)
        monkeypatch.setenv("ENCRYPTION_KEY", "b" * 44)
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test-key")
        result = runner.invoke(app, ["--check-env"])
        assert result.exit_code == 0

    def test_check_env_output_contains_table(self, monkeypatch):
        """--check-env output must contain variable names and status symbols."""
        monkeypatch.setenv("SECRET_KEY", "a" * 64)
        monkeypatch.setenv("ENCRYPTION_KEY", "b" * 44)
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-test-key")
        result = runner.invoke(app, ["--check-env"])
        assert "SECRET_KEY" in result.output
        assert "ANTHROPIC_API_KEY" in result.output
        assert "ENCRYPTION_KEY" in result.output

    def test_check_env_missing_vars_shows_cross_symbol(self, monkeypatch):
        """--check-env output must show ✗ for missing required vars."""
        monkeypatch.delenv("SECRET_KEY", raising=False)
        result = runner.invoke(app, ["--check-env"])
        # Rich may strip ANSI in test runner — check for the cross symbol
        assert "✗" in result.output or "NOT SET" in result.output
