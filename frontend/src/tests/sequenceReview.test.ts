import { describe, expect, it } from "vitest";
import {
  canLaunch,
  overrideReasonError,
  reviewHeadline,
  severityTone,
  sortFindings,
  type ReviewFinding,
  type SequenceReview,
} from "@/lib/sequenceReview";

function finding(overrides: Partial<ReviewFinding>): ReviewFinding {
  return { id: Math.random().toString(36), step_no: 1, severity: "warn", category: "tone",
           code: "tone:x", message: "m", evidence: null, source: "rules", ...overrides };
}

function review(overrides: Partial<SequenceReview>): SequenceReview {
  return { id: "r", sequence_id: "s", status: "passed", is_current: true, blocking_count: 0,
           warning_count: 0, reviewer: "rules", findings: [], created_at: null,
           override_reason: null, overridden_at: null, overridden_by_user_id: null, ...overrides };
}

describe("sortFindings", () => {
  it("puts blocking issues first, then by step", () => {
    const sorted = sortFindings([
      finding({ severity: "info", step_no: null, code: "c" }),
      finding({ severity: "warn", step_no: 2, code: "b" }),
      finding({ severity: "block", step_no: 3, code: "a" }),
      finding({ severity: "block", step_no: 1, code: "z" }),
    ]);
    expect(sorted.map((f) => [f.severity, f.step_no])).toEqual([
      ["block", 1], ["block", 3], ["warn", 2], ["info", null]]);
  });
});

describe("headline and launch state", () => {
  it("says what a person needs to do", () => {
    expect(reviewHeadline(null)).toBe("Not reviewed yet");
    expect(reviewHeadline(review({ status: "blocked", blocking_count: 2 })))
      .toBe("2 blocking issues — fix or override to launch");
    expect(reviewHeadline(review({ warning_count: 1 }))).toBe("Ready to launch · 1 warning");
    expect(reviewHeadline(review({ is_current: false }))).toBe("Content changed since the last review");
    expect(reviewHeadline(review({ status: "overridden" }))).toBe("Launched with an override");
  });
  it("only lets current, unblocked reviews launch", () => {
    expect(canLaunch(review({}))).toBe(true);
    expect(canLaunch(review({ status: "overridden" }))).toBe(true);
    expect(canLaunch(review({ status: "blocked" }))).toBe(false);
    expect(canLaunch(review({ is_current: false }))).toBe(false);
    expect(canLaunch(undefined)).toBe(false);
  });
});

describe("misc", () => {
  it("tones severities", () => {
    expect(severityTone("block")).toBe("destructive");
    expect(severityTone("warn")).toBe("warning");
    expect(severityTone("info")).toBe("default");
  });
  it("requires a real override reason", () => {
    expect(overrideReasonError("ok")).toMatch(/at least 10/);
    expect(overrideReasonError("  verified with the client  ")).toBeNull();
  });
});
