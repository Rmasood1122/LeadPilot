"""Load the native agent cores, or fall back to the Python reference.

    rs   -- vectorae_native_rs  (Rust, native/rust): prioritize_leads,
            next_followup_slot, top_reply_slots, evaluate_agent
    cpp  -- vectorae_native_cpp (C++, native/cpp):   assess_mailbox,
            triage_reply, check_claims

Both expose exactly the function names of app/agents/reference.py, so callers
use `native.rs.<fn>` / `native.cpp.<fn>` and never branch on the backend.

VECTORAE_REQUIRE_NATIVE=1 (set in the Docker image and in the CI job that
builds the wheels) turns a missing module into an ImportError at import time,
so a production process can never quietly run the fallback.
"""

from __future__ import annotations

import logging
import os
from types import ModuleType

from app.agents import reference

logger = logging.getLogger(__name__)

REQUIRE_ENV = "VECTORAE_REQUIRE_NATIVE"


def _load(name: str) -> tuple[ModuleType, str]:
    try:
        module = __import__(name)
    except ImportError:
        if os.environ.get(REQUIRE_ENV) == "1":
            raise ImportError(f"{name} is not installed and {REQUIRE_ENV}=1; build it "
                              f"with `pip install ./native/{'rust' if name.endswith('rs') else 'cpp'}`")
        logger.info("agents: %s not installed, using the Python reference", name)
        return reference, "python"
    return module, "native"


rs, RS_BACKEND = _load("vectorae_native_rs")
cpp, CPP_BACKEND = _load("vectorae_native_cpp")


def backends() -> dict[str, str]:
    return {"rust": RS_BACKEND, "cpp": CPP_BACKEND}
