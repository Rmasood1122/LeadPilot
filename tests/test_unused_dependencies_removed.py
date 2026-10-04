"""F-OPS-07 / F-OPS-06 (unused deps) -- do not ship what the code never imports.

python-jose (JWTs use PyJWT; jose is vestigial and has had CVEs), pandas, and
the Google API client trio (google-auth, google-auth-oauthlib,
google-api-python-client) were declared in requirements.txt only. No module
imports them, and the production image installs from pyproject.toml, where they
were never declared. Each extra package is attack surface and install time for
nothing.

google-auth still arrives TRANSITIVELY through firebase-admin; it is just no
longer a direct requirement we claim to use.
"""

from __future__ import annotations

import ast
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

REPO = Path(__file__).resolve().parent.parent

UNUSED = {"python-jose", "pandas", "google-auth", "google-auth-oauthlib",
          "google-api-python-client"}
#: top-level module names those distributions provide
MODULES = {"jose", "pandas", "google.auth", "google.oauth2", "google_auth_oauthlib",
           "googleapiclient"}


def _declared(path: Path) -> set[str]:
    names = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            names.add(canonicalize_name(Requirement(line).name))
    return names


def test_requirements_txt_does_not_declare_the_unused_packages():
    assert _declared(REPO / "requirements.txt") & UNUSED == set()


def test_pyproject_does_not_declare_them_either():
    import tomllib
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    deps = list(data["project"]["dependencies"])
    for extra in data["project"].get("optional-dependencies", {}).values():
        deps += extra
    declared = {canonicalize_name(Requirement(d).name) for d in deps}
    assert declared & UNUSED == set()


def _imported_modules(tree: ast.AST) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def test_nothing_in_the_repo_imports_them():
    """The claim that makes removal safe, checked rather than asserted."""
    this = Path(__file__).resolve()
    offenders = []
    for folder in ("app", "scripts", "alembic", "tests"):
        for path in (REPO / folder).rglob("*.py"):
            if path.resolve() == this or "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for mod in _imported_modules(tree):
                if any(mod == m or mod.startswith(m + ".") for m in MODULES):
                    offenders.append(f"{path.relative_to(REPO)}: {mod}")
    assert offenders == [], offenders
