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

from datetime import datetime, timedelta, timezone

from app.db.models import Strategy, StrategyStatus
from app.verification.passes import build_passes

MAX_OVERRIDABLE = 3
MIN_REASON_CHARS = 20
# Never overridable by a human. Keyed by pass key, not number, so a renumbering
# cannot silently unprotect it.
PROTECTED_KEYS = frozenset({"legal_compliance"})


# A verification that has logged nothing for this long is not running any more.
# One judge+fix cycle is about 3-4 minutes, so 15 minutes of silence means the
# worker was killed or restarted, not that it is busy.
STALE_AFTER = timedelta(minutes=15)


class OverrideRefused(Exception):
    """The override is not allowed. `status` is the HTTP code to answer with."""

    def __init__(self, detail: str, status: int = 409):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def failing_passes(log: list[dict] | None) -> dict[int, dict]:
    """pass_no -> its latest log entry, for passes whose latest entry is FAIL.
    `log` should be ONE run (see latest_complete_run), not the whole history."""
    latest: dict[int, dict] = {}
    for entry in log or []:
        latest[entry["pass_no"]] = entry
    return {n: e for n, e in latest.items() if e.get("result") == "FAIL"}


def split_runs(log: list[dict] | None) -> list[list[dict]]:
    """Split the pass log into verification runs.

    verified_passes_json is append-only across runs, and one run walks the
    passes in order, so a pass number that goes backwards (or the same pass
    starting over at attempt 1) is a new run. Manual-override entries are not
    part of any run.
    """
    runs: list[list[dict]] = []
    prev = None
    for entry in log or []:
        if entry.get("manual_override"):
            continue
        new_run = (
            prev is None
            or entry["pass_no"] < prev["pass_no"]
            or (entry["pass_no"] == prev["pass_no"]
                and int(entry.get("attempt", 1)) <= int(prev.get("attempt", 1)))
        )
        if new_run:
            runs.append([])
        runs[-1].append(entry)
        prev = entry
    return runs


def latest_complete_run(log: list[dict] | None, total_passes: int) -> list[dict] | None:
    """The most recent run that reached the last pass. A run cut short by a
    budget stop, a restart or a crash is not a verification result and must not
    overwrite an earlier complete one."""
    complete = None
    for run in split_runs(log):
        if {e["pass_no"] for e in run} >= set(range(1, total_passes + 1)):
            complete = run
    return complete


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _last_activity(strategy: Strategy) -> datetime | None:
    stamps = []
    if strategy.updated_at is not None:
        stamps.append(_aware(strategy.updated_at))
    for entry in strategy.verified_passes_json or []:
        ts = entry.get("ts")
        if ts:
            try:
                stamps.append(_aware(datetime.fromisoformat(ts)))
            except ValueError:
                pass
    return max(stamps) if stamps else None


def check_status_allows(strategy: Strategy, now: datetime | None = None) -> None:
    """Sign-off is allowed from needs_human_review, from budget_exhausted (the
    loop stopped and is not running), and from `verifying` ONLY when that run
    has gone quiet -- a live loop would later overwrite the decision."""
    status = strategy.status
    if status in (StrategyStatus.NEEDS_HUMAN_REVIEW, StrategyStatus.BUDGET_EXHAUSTED):
        return
    if status is StrategyStatus.VERIFYING:
        last = _last_activity(strategy)
        now = now or datetime.now(timezone.utc)
        if last is None or now - last >= STALE_AFTER:
            return
        raise OverrideRefused(
            "verification was active in the last "
            f"{int(STALE_AFTER.total_seconds() // 60)} minutes and may still be "
            "running. Wait until it stops, then try again.")
    raise OverrideRefused(
        f"strategy status is '{status.value}' - only a strategy whose "
        "verification has stopped can be signed off")


def apply_override(strategy: Strategy, *, pass_nos: list[int], reason: str,
                   user_id, user_email: str, now: datetime | None = None) -> list[int]:
    """Validate and record the override on `strategy`; returns the pass numbers
    overridden. Mutates `verified_passes_json` only -- the caller sets the status
    and commits, so a refusal leaves nothing half-written.

    The sign-off is based on the latest COMPLETE verification run; partial runs
    after it (killed by a restart, stopped by the budget) are ignored."""
    check_status_allows(strategy, now)
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON_CHARS:
        raise OverrideRefused(
            f"a written reason of at least {MIN_REASON_CHARS} characters is required",
            status=422)

    log = list(strategy.verified_passes_json or [])
    specs = {s.pass_no: s for s in build_passes(strategy.flow_type)}
    run = latest_complete_run(log, len(specs))
    if run is None:
        raise OverrideRefused(
            "no complete verification run to sign off: no run has reached all "
            f"{len(specs)} checks. Re-verify the strategy instead.")
    failing = failing_passes(run)
    if not failing:
        raise OverrideRefused("no failed pass to override")
    if len(failing) > MAX_OVERRIDABLE:
        raise OverrideRefused(
            f"{len(failing)} passes failed; a manual override covers at most "
            f"{MAX_OVERRIDABLE}. Re-verify or fix the strategy instead.")

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

    run_number = split_runs(log).index(run) + 1
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
            "based_on_run": run_number,
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
