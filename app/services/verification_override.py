"""Manual override of failed verification passes (human review).

A strategy in `needs_human_review` has one or more passes whose LAST recorded
attempt is FAIL. When only a few failed, the owner can read the failure reason
and decide to accept the strategy anyway. That decision is a human sign-off, not
a judge verdict, so it is recorded as one: every overridden pass gets a new log
entry marked `manual_override` with who, when and why, and the original FAIL
rows stay in the log untouched.

Hard limits, all enforced here so the API and any future caller share them:
  * at most MAX_OVERRIDABLE passes may be failing (more means the strategy is
    wrong, not borderline);
  * the legal & compliance pass can never be overridden -- the product's
    compliance posture is zero tolerance, so that pass has to actually pass;
  * the caller must name exactly the failing passes (no blanket approve) and
    give a written reason.
"""

from datetime import datetime, timezone

from app.db.models import Strategy
from app.verification.passes import build_passes

MAX_OVERRIDABLE = 3
MIN_REASON_CHARS = 20
# Never overridable by a human. Keyed by pass key, not number, so a renumbering
# cannot silently unprotect it.
PROTECTED_KEYS = frozenset({"legal_compliance"})


class OverrideRefused(Exception):
    """The override is not allowed. `status` is the HTTP code to answer with."""

    def __init__(self, detail: str, status: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def failing_passes(log: list[dict] | None) -> dict[int, dict]:
    """pass_no -> its latest log entry, for passes whose latest entry is FAIL."""
    latest: dict[int, dict] = {}
    for entry in log or []:
        latest[entry["pass_no"]] = entry
    return {n: e for n, e in latest.items() if e.get("result") == "FAIL"}


def apply_override(strategy: Strategy, *, pass_nos: list[int], reason: str,
                   user_id, user_email: str) -> list[int]:
    """Validate and record the override on `strategy`; returns the pass numbers
    overridden. Mutates `verified_passes_json` only -- the caller sets the status
    and commits, so a refusal leaves nothing half-written."""
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON_CHARS:
        raise OverrideRefused(
            f"a written reason of at least {MIN_REASON_CHARS} characters is required",
            status=422)

    log = list(strategy.verified_passes_json or [])
    failing = failing_passes(log)
    if not failing:
        raise OverrideRefused("no failed pass to override")
    if len(failing) > MAX_OVERRIDABLE:
        raise OverrideRefused(
            f"{len(failing)} passes failed; a manual override covers at most "
            f"{MAX_OVERRIDABLE}. Re-verify or fix the strategy instead.")

    specs = {s.pass_no: s for s in build_passes(strategy.flow_type)}
    protected = sorted(n for n in failing
                       if specs.get(n) is not None and specs[n].key in PROTECTED_KEYS)
    if protected:
        raise OverrideRefused(
            f"pass {protected[0]} (Legal & compliance) failed and cannot be "
            "overridden manually. It must pass verification.")

    if sorted(set(pass_nos)) != sorted(failing):
        raise OverrideRefused(
            f"pass_nos must list exactly the failed passes {sorted(failing)}; "
            f"got {sorted(set(pass_nos))}", status=422)

    ts = datetime.now(timezone.utc).isoformat()
    for n in sorted(failing):
        last = failing[n]
        spec = specs.get(n)
        log.append({
            "pass_no": n,
            "key": last.get("key") or (spec.key if spec else None),
            "name": last.get("name") or (spec.name if spec else None),
            "attempt": int(last.get("attempt", 0)) + 1,
            "result": "PASS",
            "outcome": "manual_override",
            "manual_override": True,
            "overridden_by": str(user_id),
            "overridden_by_email": user_email,
            "reason": reason,
            "overridden_failure": last.get("fix_description"),
            "fix_description": None,
            "fix_applied": False,
            "ts": ts,
        })
    strategy.verified_passes_json = log
    from sqlalchemy.orm.attributes import flag_modified  # noqa: PLC0415
    flag_modified(strategy, "verified_passes_json")
    return sorted(failing)
