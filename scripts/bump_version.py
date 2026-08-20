"""
Version bump script for the clienthunter pip package.

Usage:
    python scripts/bump_version.py patch    # 1.0.0 → 1.0.1
    python scripts/bump_version.py minor    # 1.0.0 → 1.1.0
    python scripts/bump_version.py major    # 1.0.0 → 2.0.0

What it does:
  1. Reads current version from sdk/pyproject.toml
  2. Bumps the requested part
  3. Writes the new version back to pyproject.toml
  4. Creates a git commit: "chore: bump SDK to vX.Y.Z"
  5. Creates a git tag: release/sdk-vX.Y.Z (triggers PyPI CI on push)
  6. Prints the push command — NEVER auto-pushes

Review the commit, then:
    git push origin release/sdk-v<NEW_VERSION>
CI does the rest (see .github/workflows/pypi-release.yml).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PYPROJECT_PATH = Path(__file__).parent.parent / "sdk" / "pyproject.toml"


def _read_version() -> str:
    text = PYPROJECT_PATH.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise ValueError("Could not find version in pyproject.toml")
    return match.group(1)


def _bump(current: str, part: str) -> str:
    parts = current.split(".")
    if len(parts) != 3:
        raise ValueError(f"Expected semver X.Y.Z, got: {current}")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unknown bump part: {part}. Use major|minor|patch")


def _write_version(new_version: str) -> None:
    text = PYPROJECT_PATH.read_text()
    updated = re.sub(
        r'^(version\s*=\s*")[^"]+(")',
        rf'\g<1>{new_version}\g<2>',
        text,
        flags=re.MULTILINE,
    )
    if updated == text:
        raise ValueError("Version replacement had no effect — check pyproject.toml format")
    PYPROJECT_PATH.write_text(updated)


def _git(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"git error: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("major", "minor", "patch"):
        print("Usage: python scripts/bump_version.py major|minor|patch", file=sys.stderr)
        sys.exit(1)

    part = sys.argv[1]

    if not PYPROJECT_PATH.exists():
        print(f"Not found: {PYPROJECT_PATH}", file=sys.stderr)
        sys.exit(1)

    current = _read_version()
    new_version = _bump(current, part)

    print(f"Bumping SDK version: {current} → {new_version}")
    _write_version(new_version)
    print(f"  ✓ Updated {PYPROJECT_PATH}")

    tag = f"release/sdk-v{new_version}"
    commit_msg = f"chore: bump SDK to v{new_version}"

    _git(["git", "add", str(PYPROJECT_PATH)])
    _git(["git", "commit", "-m", commit_msg])
    _git(["git", "tag", tag])

    print(f"  ✓ Committed: \"{commit_msg}\"")
    print(f"  ✓ Tagged: {tag}")
    print()
    print("Review the commit above, then push to trigger CI:")
    print(f"    git push origin {tag}")
    print()
    print("CI will: TestPyPI smoke test → PyPI publish (see .github/workflows/pypi-release.yml)")


if __name__ == "__main__":
    main()
