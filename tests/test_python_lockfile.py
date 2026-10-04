"""F-OPS-06 -- requirements.lock must agree with pyproject.toml.

The 3-week outage was a manifest that let the image resolve a version the tests
never ran (SQLAlchemy 2.1). A lockfile only helps if it cannot silently drift
from the manifest, so this pins:

  * every line is an exact `==` pin (nothing floats);
  * every direct dependency in pyproject.toml is locked, at a version its own
    specifier accepts;
  * packages removed under F-OPS-07 (python-jose, pandas, the Google client
    trio) are not locked as direct installs of ours.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

REPO = Path(__file__).resolve().parent.parent


def _lock() -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw in (REPO / "requirements.lock").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        assert "==" in line and ">" not in line and "<" not in line, f"not an exact pin: {raw!r}"
        req = Requirement(line)
        pins[canonicalize_name(req.name)] = next(iter(req.specifier)).version
    return pins


def _direct() -> list[Requirement]:
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return [Requirement(d) for d in data["project"]["dependencies"]]


def test_every_line_is_an_exact_pin():
    assert len(_lock()) > 50


def test_every_direct_dependency_is_locked_within_its_specifier():
    pins = _lock()
    problems = []
    for req in _direct():
        name = canonicalize_name(req.name)
        if name not in pins:
            problems.append(f"{req.name}: not locked")
        elif not req.specifier.contains(Version(pins[name]), prereleases=True):
            problems.append(f"{req.name}: locked {pins[name]} outside {req.specifier}")
    assert problems == [], problems


def test_the_sqlalchemy_that_caused_the_outage_cannot_be_locked():
    version = Version(_lock()["sqlalchemy"])
    assert Version("2.0.30") <= version < Version("2.1")


def test_the_postgres_driver_the_image_ships_is_locked():
    assert "psycopg2-binary" in _lock()
    assert "psycopg" not in _lock()


def test_packages_removed_by_f_ops_07_are_not_locked():
    pins = _lock()
    assert not ({"python-jose", "pandas", "google-api-python-client",
                 "google-auth-oauthlib"} & set(pins))
