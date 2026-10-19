"""The master agent: runs the five agents and watches their health.

Every run goes through `run_agent`, which
  1. asks the Rust supervisor (evaluate_agent, native/rust/src/supervisor.rs)
     whether the agent's circuit lets it run -- after 3 consecutive failures
     it is OPEN for 5 minutes, then HALF-OPEN for one trial run;
  2. times the run and records it in `agent_runs` (agent, ok, latency, which
     backend ran it, a short error class -- never request data);
  3. on a failure that opens the circuit, logs an `agent_circuit_opened`
     alert at ERROR level, which the existing log alerting picks up.

Health is system-wide (an agent is broken for everyone or no one), computed
from the agent's last HISTORY runs across accounts; it carries no account
data, only counts, rates and latencies.

Bad input (a malformed parameter -> ValueError) is the caller's mistake, not
the agent's: it is not recorded and cannot trip the breaker.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import (
    claim_check, deliverability_guard, followup_timing, lead_priority, native, reply_triage,
)
from app.agents.base import AgentSpec, aware, now
from app.db.models import AgentRun, User

logger = logging.getLogger(__name__)

HISTORY = 50
FAILURE_THRESHOLD = 3
COOLDOWN_S = 300.0
LATENCY_BUDGET_MS = 5000.0

AGENTS: dict[str, AgentSpec] = {spec.name: spec for spec in (
    AgentSpec(lead_priority.NAME, "Lead Priority", "rust",
              "Ranks leads by who to work next and names the next action.", lead_priority.run),
    AgentSpec(followup_timing.NAME, "Follow-up Timing", "rust",
              "Learns when your prospects reply and picks the next follow-up slot.",
              followup_timing.run),
    AgentSpec(deliverability_guard.NAME, "Deliverability Guard", "cpp",
              "Scores each mailbox's bounce and opt-out risk and recommends a daily cap.",
              deliverability_guard.run),
    AgentSpec(reply_triage.NAME, "Reply Triage", "cpp",
              "Re-reads recent replies and flags opt-outs the stored classification missed.",
              reply_triage.run),
    AgentSpec(claim_check.NAME, "Claim & Compliance Check", "cpp",
              "Flags risky claims and deceptive subjects in drafts before they are approved.",
              claim_check.run),
)}


class UnknownAgent(KeyError):
    pass


class CircuitOpen(RuntimeError):
    def __init__(self, health: dict):
        super().__init__(health["reason"])
        self.health = health


class AgentFailed(RuntimeError):
    pass


def _backend(spec: AgentSpec) -> str:
    return native.backends()["rust" if spec.language == "rust" else "cpp"]


def health(db: Session, name: str) -> dict:
    rows = db.execute(select(AgentRun.ok, AgentRun.latency_ms, AgentRun.started_at)
                      .where(AgentRun.agent == name)
                      .order_by(AgentRun.started_at.desc(), AgentRun.id.desc())
                      .limit(HISTORY)).all()
    t = now()
    runs = [(bool(ok), float(latency), max(0.0, (t - aware(started)).total_seconds()))
            for ok, latency, started in rows]
    return dict(native.rs.evaluate_agent(runs, FAILURE_THRESHOLD, COOLDOWN_S,
                                         LATENCY_BUDGET_MS, 0.3, 0.3))


def _record(db: Session, user: User, spec: AgentSpec, ok: bool, latency_ms: float,
            items: int = 0, error: str | None = None) -> None:
    db.add(AgentRun(user_id=user.id, agent=spec.name, ok=ok, latency_ms=latency_ms,
                    backend=_backend(spec), items=items,
                    error=error[:300] if error else None, started_at=now()))
    db.commit()


def run_agent(db: Session, user: User, name: str, params: dict | None = None) -> dict:
    spec = AGENTS.get(name)
    if spec is None:
        raise UnknownAgent(name)
    before = health(db, name)
    if not before["may_run"]:
        raise CircuitOpen(before)
    started = time.perf_counter()
    try:
        out = spec.run(db, user, params or {})
    except ValueError:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001 -- every agent failure is recorded, then re-raised
        db.rollback()
        latency = (time.perf_counter() - started) * 1000.0
        _record(db, user, spec, False, latency, error=f"{type(exc).__name__}: {exc}")
        after = health(db, name)
        if after["circuit"] == "open" and before["circuit"] != "open":
            logger.error("agent_circuit_opened agent=%s consecutive_failures=%s reason=%s",
                         name, after["consecutive_failures"], after["reason"])
        raise AgentFailed(f"{spec.title} failed") from exc
    latency = (time.perf_counter() - started) * 1000.0
    _record(db, user, spec, True, latency, items=out.items)
    return {"agent": name, "title": spec.title, "language": spec.language,
            "backend": _backend(spec), "latency_ms": round(latency, 2), "items": out.items,
            "result": out.result}


_RANK = {"idle": 0, "healthy": 0, "degraded": 1, "down": 2}


def status(db: Session) -> dict:
    agents = []
    for spec in AGENTS.values():
        agents.append({"name": spec.name, "title": spec.title, "language": spec.language,
                       "description": spec.description, "backend": _backend(spec),
                       "health": health(db, spec.name)})
    worst = max((_RANK[a["health"]["status"]] for a in agents), default=0)
    overall = {0: "healthy", 1: "degraded", 2: "down"}[worst]
    return {"master": {"status": overall, "language": "rust",
                       "backend": native.backends()["rust"],
                       "policy": {"failure_threshold": FAILURE_THRESHOLD,
                                  "cooldown_s": COOLDOWN_S,
                                  "latency_budget_ms": LATENCY_BUDGET_MS,
                                  "history": HISTORY}},
            "agents": agents}
