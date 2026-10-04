/**
 * Re-verify button contract: offered only for needs_human_review (the server
 * refuses every other status with 409), and the budget field parses safely.
 */
import { describe, it, expect } from "vitest";
import { canReverify, parseBudget } from "@/components/strategy/ReverifyStrategyButton";

describe("re-verify offer", () => {
  it("is offered only when waiting for human review", () => {
    expect(canReverify("needs_human_review")).toBe(true);
    for (const s of ["pending", "researching", "verifying", "verified",
                     "failed", "executing", "budget_exhausted"] as const) {
      expect(canReverify(s)).toBe(false);
    }
  });
});

describe("parseBudget", () => {
  it("treats blank as unchanged", () => expect(parseBudget("  ")).toBeUndefined());
  it("accepts a positive number", () => expect(parseBudget("6.5")).toBe(6.5));
  it("rejects zero, negatives and junk", () => {
    expect(parseBudget("0")).toBeNull();
    expect(parseBudget("-2")).toBeNull();
    expect(parseBudget("abc")).toBeNull();
  });
});
