"""F-OPS-01 — firebase-admin must be declared where the Dockerfile installs from.

The Dockerfile runs `pip install .`, which reads pyproject.toml, not
requirements.txt. firebase-admin was only in requirements.txt, so the
production image had no firebase_admin and push notifications could not be
sent from any container.

This pins the one dependency this finding is about. It deliberately does NOT
assert that the two files agree in general -- they do not, and that wider
mismatch is reported for triage rather than fixed here.
"""

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _name(spec: str) -> str:
    return re.split(r"[\[<>=!~; ]", spec.strip(), maxsplit=1)[0].lower().replace("_", "-")


def _requirements() -> dict:
    found = {}
    for line in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line and not line.startswith("-"):
            found[_name(line)] = line.replace(" ", "")
    return found


def _pyproject_dependencies() -> dict:
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return {_name(spec): spec.replace(" ", "") for spec in project["dependencies"]}


def test_firebase_admin_is_a_runtime_dependency_in_pyproject():
    assert "firebase-admin" in _pyproject_dependencies()


def test_its_version_spec_matches_requirements_txt():
    assert _requirements()["firebase-admin"] == "firebase-admin>=6.5.0"
    assert _pyproject_dependencies().get("firebase-admin") == _requirements()["firebase-admin"]


def test_the_dockerfile_installs_from_pyproject():
    """The reason the declaration has to be in pyproject.toml at all."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY pyproject.toml" in dockerfile
    assert "pip install ." in dockerfile
    assert "requirements.txt" not in dockerfile


def test_the_code_that_needs_it_exists():
    source = (REPO / "app" / "services" / "notifications.py").read_text(encoding="utf-8")
    assert "firebase_admin" in source
