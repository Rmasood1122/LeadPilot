import type { VerificationPass } from "@/lib/api/types";

/** Mirrors app/services/verification_override.py. The server enforces these;
 *  the UI uses them only to decide what to offer. */
export const MAX_OVERRIDABLE = 3;
export const MIN_REASON_CHARS = 20;
export const PROTECTED_KEYS = ["legal_compliance"];

/** The log has one row per attempt. The latest row per pass is its state. */
export function latestPerPass(log: VerificationPass[]): VerificationPass[] {
  const latest = new Map<number, VerificationPass>();
  for (const row of log) latest.set(row.pass_no, row);
  return [...latest.values()].sort((a, b) => a.pass_no - b.pass_no);
}

export function failedPasses(log: VerificationPass[]): VerificationPass[] {
  return latestPerPass(log).filter((p) => p.result === "FAIL");
}

export type OverrideOffer =
  | { kind: "none" }
  | { kind: "blocked"; reason: string }
  | { kind: "allowed"; passes: VerificationPass[] };

/** What the review panel may offer. `blocked` explains why a sign-off is not
 *  possible; the Legal & compliance pass is never overridable. */
export function overrideOffer(log: VerificationPass[]): OverrideOffer {
  const failed = failedPasses(log);
  if (failed.length === 0) return { kind: "none" };
  if (failed.some((p) => p.key !== undefined && PROTECTED_KEYS.includes(p.key))) {
    return {
      kind: "blocked",
      reason:
        "The Legal & compliance check failed. It cannot be passed manually: " +
        "fix the strategy or re-verify it.",
    };
  }
  if (failed.length > MAX_OVERRIDABLE) {
    return {
      kind: "blocked",
      reason:
        `${failed.length} checks failed. A manual sign-off covers at most ` +
        `${MAX_OVERRIDABLE}. Re-verify or fix the strategy instead.`,
    };
  }
  return { kind: "allowed", passes: failed };
}

export function reasonOk(reason: string): boolean {
  return reason.trim().length >= MIN_REASON_CHARS;
}

// ---------------------------------------------------------------------------
// Run-aware review. The log is append-only across verification runs, and a run
// cut short (budget stop, worker restart) must not overwrite an earlier
// complete one. Mirrors app/services/verification_override.py.
// ---------------------------------------------------------------------------

export const VERIFYING_STALE_NOTE =
  "If a verification is still running, the server will refuse until it has " +
  "been quiet for 15 minutes.";

/** Statuses from which the server may accept a sign-off. `verifying` is only
 *  accepted once the run has gone quiet; the server decides that. */
export const SIGNOFF_STATUSES = ["needs_human_review", "budget_exhausted", "verifying"] as const;

export function splitRuns(log: VerificationPass[]): VerificationPass[][] {
  const runs: VerificationPass[][] = [];
  let prev: VerificationPass | undefined;
  for (const row of log) {
    if (row.manual_override) continue;
    const newRun =
      prev === undefined ||
      row.pass_no < prev.pass_no ||
      (row.pass_no === prev.pass_no && (row.attempt ?? 1) <= (prev.attempt ?? 1));
    if (newRun) runs.push([]);
    runs[runs.length - 1].push(row);
    prev = row;
  }
  return runs;
}

/** The most recent run that reached every check, or null. */
export function latestCompleteRun(
  log: VerificationPass[],
  totalPasses = 10,
): VerificationPass[] | null {
  let complete: VerificationPass[] | null = null;
  for (const run of splitRuns(log)) {
    const seen = new Set(run.map((r) => r.pass_no));
    let all = true;
    for (let n = 1; n <= totalPasses; n++) if (!seen.has(n)) all = false;
    if (all) complete = run;
  }
  return complete;
}

export type RunOverrideOffer =
  | { kind: "none" }
  | { kind: "blocked"; reason: string }
  | { kind: "allowed"; passes: VerificationPass[] };

export function runOverrideOffer(
  log: VerificationPass[],
  totalPasses = 10,
): RunOverrideOffer {
  const run = latestCompleteRun(log, totalPasses);
  if (run === null) {
    return {
      kind: "blocked",
      reason:
        "No verification run has reached all 10 checks, so there is nothing to " +
        "sign off. Re-verify the strategy instead.",
    };
  }
  const offer = overrideOffer(run);
  return offer as RunOverrideOffer;
}
