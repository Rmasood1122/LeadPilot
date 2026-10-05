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
