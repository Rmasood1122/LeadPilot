"""Single source of version truth.

Referenced by pyproject.toml via:
    [tool.setuptools.dynamic]
    version = { attr = "clienthunter._version.__version__" }

Bump here only; the wheel + importlib.metadata stay in sync automatically.
"""

__version__ = "0.1.0"
