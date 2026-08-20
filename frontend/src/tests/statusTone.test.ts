/**
 * statusTone — every status the backend can emit must render meaningfully.
 *
 * `failed` was the case that mattered: StrategyStatus.FAILED existed in the
 * backend enum, types.ts declared it, and statusTone() already mapped it to
 * `destructive` — but nothing in app/ ever ASSIGNED it, so the red badge was
 * unreachable. A permanently-broken pipeline showed the user an in-progress
 * spinner forever instead. The backend now sets FAILED at both give-up points
 * (non-retryable error, retries exhausted).
 *
 * These tests pin the frontend half of that contract so the two sides cannot
 * drift apart again.
 */

import { describe, it, expect } from "vitest";
import { statusTone } from "@/components/ui/badge";
import type { Strategy } from "@/lib/api/types";

// Every member of the backend's StrategyStatus enum (app/db/models.py).
// Keep in sync with types.ts's Strategy["status"] union.
const STRATEGY_STATUSES: Array<Strategy["status"]> = [
  "pending",
  "researching",
  "verifying",
  "verified",
  "needs_human_review",
  "executing",
  "failed",
];

describe("statusTone — strategy statuses", () => {
  it("maps a failed strategy to the destructive tone", () => {
    // The whole point of the terminal-state fix: this is now reachable.
    expect(statusTone("failed")).toBe("destructive");
  });

  it("does not render a failed strategy as in-progress", () => {
    // The bug's user-visible symptom was a stuck in-progress badge.
    expect(statusTone("failed")).not.toBe(statusTone("researching"));
    expect(statusTone("failed")).not.toBe(statusTone("verifying"));
  });

  it("distinguishes failure from success", () => {
    expect(statusTone("failed")).not.toBe(statusTone("verified"));
  });

  it("gives needs_human_review a warning tone, not a failure tone", () => {
    // needs_human_review is a finished strategy awaiting a person — it is not
    // the same outcome as a pipeline that died.
    expect(statusTone("needs_human_review")).toBe("warning");
    expect(statusTone("needs_human_review")).not.toBe(statusTone("failed"));
  });

  it.each(STRATEGY_STATUSES)("resolves a tone for %s", (status) => {
    expect(typeof statusTone(status)).toBe("string");
    expect(statusTone(status).length).toBeGreaterThan(0);
  });

  it("gives terminal-good, terminal-bad and in-progress distinct tones", () => {
    const verified = statusTone("verified");
    const failed = statusTone("failed");
    const researching = statusTone("researching");
    expect(new Set([verified, failed, researching]).size).toBe(3);
  });
});
