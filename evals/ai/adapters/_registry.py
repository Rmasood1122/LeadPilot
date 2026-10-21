"""The adapter registry shared by every adapters/ module."""

from __future__ import annotations

from typing import Any, Callable

ADAPTERS: dict[str, Callable[[dict, Any], Any]] = {}


def adapter(name: str):
    def register(fn):
        if name in ADAPTERS:
            raise ValueError(f"adapter {name!r} registered twice")
        ADAPTERS[name] = fn
        return fn
    return register
