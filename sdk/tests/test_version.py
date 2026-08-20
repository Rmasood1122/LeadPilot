"""Version single-sourcing tests.

Verifies that the version string in ``clienthunter._version.__version__``
is the same value that ``importlib.metadata`` exposes for the installed package.

This test FAILS if:
- pyproject.toml's ``[tool.setuptools.dynamic] version`` points somewhere wrong
- The package was installed before a version bump (stale wheel)
- ``__version__`` was changed directly without bumping pyproject.toml (n/a here
  since the single source IS _version.py)
"""
import importlib.metadata

import clienthunter
from clienthunter._version import __version__


def test_version_single_sourcing():
    """importlib.metadata version matches the __version__ constant."""
    meta_version = importlib.metadata.version("clienthunter")
    assert meta_version == __version__, (
        f"Installed package version ({meta_version!r}) does not match "
        f"clienthunter.__version__ ({__version__!r}).\n"
        "Run `pip install -e .` from the sdk/ directory to sync."
    )


def test_version_accessible_from_package():
    """__version__ is re-exported at the package root."""
    assert hasattr(clienthunter, "__version__")
    assert clienthunter.__version__ == __version__


def test_version_format():
    """Version is a valid PEP 440 string (major.minor.patch at minimum)."""
    parts = __version__.split(".")
    assert len(parts) >= 2, f"Expected at least major.minor, got {__version__!r}"
    for part in parts[:3]:
        base = part.split("a")[0].split("b")[0].split("rc")[0].split(".dev")[0]
        assert base.isdigit(), f"Non-numeric version component: {part!r}"
