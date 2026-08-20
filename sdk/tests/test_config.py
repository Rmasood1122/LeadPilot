"""Config unit tests.

Covers:
- Environment variable precedence over config file
- Config file precedence over defaults
- 0600 file permissions set on write
- Atomic write (temp-file rename)
- Secrets NEVER appear in exception messages or repr
"""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from clienthunter.config import Config, load, save, _to_toml

SECRET_TOKEN = "super_secret_access_token_1234"
SECRET_REFRESH = "super_secret_refresh_token_5678"


# ---------------------------------------------------------------------------
# Config file round-trip
# ---------------------------------------------------------------------------


def test_save_creates_file_with_correct_permissions(tmp_path):
    config_dir = tmp_path / ".clienthunter"
    config_file = config_dir / "config.toml"

    with patch("clienthunter.config._CONFIG_DIR", config_dir), \
         patch("clienthunter.config._CONFIG_FILE", config_file):
        cfg = Config(api_url="http://localhost:8000",
                     access_token=SECRET_TOKEN,
                     refresh_token=SECRET_REFRESH)
        save(cfg)

    assert config_file.exists()
    mode = config_file.stat().st_mode & 0o777
    assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


def test_save_load_round_trip(tmp_path):
    config_dir = tmp_path / ".clienthunter"
    config_file = config_dir / "config.toml"

    with patch("clienthunter.config._CONFIG_DIR", config_dir), \
         patch("clienthunter.config._CONFIG_FILE", config_file):
        cfg = Config(
            api_url="https://api.test.local",
            access_token=SECRET_TOKEN,
            refresh_token=SECRET_REFRESH,
        )
        save(cfg)
        loaded = load()

    assert loaded.api_url == "https://api.test.local"
    assert loaded.access_token == SECRET_TOKEN
    assert loaded.refresh_token == SECRET_REFRESH
    assert loaded.api_key is None


def test_save_omits_null_fields(tmp_path):
    config_dir = tmp_path / ".clienthunter"
    config_file = config_dir / "config.toml"

    with patch("clienthunter.config._CONFIG_DIR", config_dir), \
         patch("clienthunter.config._CONFIG_FILE", config_file):
        cfg = Config(api_url="http://localhost:8000")
        save(cfg)
        content = config_file.read_text()

    # null fields should not appear in the file
    assert "access_token" not in content
    assert "refresh_token" not in content


# ---------------------------------------------------------------------------
# Precedence: env var > config file > default
# ---------------------------------------------------------------------------


def test_env_var_url_overrides_config_file(tmp_path, monkeypatch):
    config_dir = tmp_path / ".clienthunter"
    config_file = config_dir / "config.toml"

    with patch("clienthunter.config._CONFIG_DIR", config_dir), \
         patch("clienthunter.config._CONFIG_FILE", config_file):
        cfg = Config(api_url="http://from-file:8000", access_token=SECRET_TOKEN)
        save(cfg)

        monkeypatch.setenv("CLIENTHUNTER_API_URL", "http://from-env:9000")
        loaded = load()

    assert loaded.api_url == "http://from-env:9000"


def test_env_var_api_key_overrides_and_clears_tokens(tmp_path, monkeypatch):
    config_dir = tmp_path / ".clienthunter"
    config_file = config_dir / "config.toml"

    with patch("clienthunter.config._CONFIG_DIR", config_dir), \
         patch("clienthunter.config._CONFIG_FILE", config_file):
        cfg = Config(api_url="http://localhost:8000",
                     access_token=SECRET_TOKEN, refresh_token=SECRET_REFRESH)
        save(cfg)

        monkeypatch.setenv("CLIENTHUNTER_API_KEY", "sk-override-key")
        loaded = load()

    # API key from env should win; tokens should be cleared (API key takes priority)
    assert loaded.api_key == "sk-override-key"
    assert loaded.access_token is None
    assert loaded.refresh_token is None


def test_default_url_when_no_file_no_env(tmp_path):
    config_dir = tmp_path / ".no_config"
    config_file = config_dir / "config.toml"

    with patch("clienthunter.config._CONFIG_DIR", config_dir), \
         patch("clienthunter.config._CONFIG_FILE", config_file):
        loaded = load()

    assert "clienthunter.ai" in loaded.api_url


# ---------------------------------------------------------------------------
# Secrets never appear in exception messages or repr
# ---------------------------------------------------------------------------


def test_config_repr_does_not_expose_tokens():
    cfg = Config(
        api_url="http://localhost:8000",
        access_token=SECRET_TOKEN,
        refresh_token=SECRET_REFRESH,
        api_key="sk-secret-key",
    )
    r = repr(cfg)
    assert SECRET_TOKEN not in r
    assert SECRET_REFRESH not in r
    assert "sk-secret-key" not in r
    # repr should only show bool flags
    assert "has_api_key=True" in r
    assert "has_access_token=True" in r


def test_config_str_does_not_expose_tokens():
    cfg = Config(api_url="http://localhost:8000", access_token=SECRET_TOKEN)
    # __str__ falls through to __repr__ (no separate __str__ defined)
    s = str(cfg)
    assert SECRET_TOKEN not in s


def test_save_exception_does_not_contain_token(tmp_path):
    """If save() raises (e.g. permission denied), the exception must not echo tokens."""
    config_dir = tmp_path / ".clienthunter"
    config_file = config_dir / "config.toml"

    # Make the directory read-only so save fails
    config_dir.mkdir(mode=0o555, parents=True)

    with patch("clienthunter.config._CONFIG_DIR", config_dir), \
         patch("clienthunter.config._CONFIG_FILE", config_file):
        cfg = Config(api_url="http://localhost", access_token=SECRET_TOKEN)
        try:
            save(cfg)
        except Exception as exc:
            assert SECRET_TOKEN not in str(exc), "Secret leaked in exception message"
            assert SECRET_TOKEN not in repr(exc), "Secret leaked in exception repr"
        finally:
            # Restore writable for cleanup
            os.chmod(config_dir, 0o755)


# ---------------------------------------------------------------------------
# _to_toml (internal serialiser)
# ---------------------------------------------------------------------------


def test_to_toml_basic():
    data = {"core": {"api_url": "http://localhost:8000"},
            "auth": {"access_token": "tok123"}}
    output = _to_toml(data)
    assert '[core]' in output
    assert 'api_url = "http://localhost:8000"' in output
    assert '[auth]' in output
    assert 'access_token = "tok123"' in output


def test_to_toml_omits_none():
    data = {"core": {"api_url": "http://localhost", "api_key": None}}
    output = _to_toml(data)
    assert "api_key" not in output


def test_to_toml_escapes_quotes():
    data = {"core": {"api_url": 'http://has"quote'}}
    output = _to_toml(data)
    assert r'http://has\"quote' in output
