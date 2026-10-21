"""One adapter per touchpoint: (case input, model client) -> the app's output.

Each adapter calls the SAME function production calls, with every
get_client() pointed at `client` (context.use_client). It returns what the
app returns after its own parsing, coercion and guards -- the thing a user
or a send path actually receives -- so graders judge the product, not the
raw model text. Records an adapter needs are seeded in a fresh in-memory
database (context.fresh_session); inputs are synthetic.

Names here are the `adapter:` values in evals/ai/golden/*.yaml. Every
module in this package is imported, so a new module registers itself.
"""

from __future__ import annotations

import importlib
import pkgutil

from evals.ai.adapters._registry import ADAPTERS, adapter

for _mod in pkgutil.iter_modules(__path__):
    if not _mod.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_mod.name}")

__all__ = ["ADAPTERS", "adapter"]
