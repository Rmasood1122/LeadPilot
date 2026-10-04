/**
 * Resume button contract: which statuses offer it, which warn, and how the
 * server's refusals are worded. The server (POST /strategies/{id}/resume)
 * refuses verified / needs_human_review / executing; the UI must not offer it.
 */
import { describe, it, expect } from "vitest";
import { ApiError } from "@/lib/api/client";
import { resumeStrategyErrorMessage } from "@/lib/api/strategies";
import {
  RESUMABLE_STATUSES,
  needsLiveRunWarning,
} from "@/components/strategy/ResumeStrategyButton";

describe("resume offer", () => {
  it("is offered for stalled or stopped runs only", () => {
    expect(RESUMABLE_STATUSES).toEqual(
      expect.arrayContaining(["researching", "verifying", "failed", "budget_exhausted", "pending"]),
    );
    for (const s of ["verified", "needs_human_review", "executing"] as const) {
      expect(RESUMABLE_STATUSES).not.toContain(s);
    }
  });

  it("warns before resuming a run that may still be alive", () => {
    expect(needsLiveRunWarning("researching")).toBe(true);
    expect(needsLiveRunWarning("verifying")).toBe(true);
    expect(needsLiveRunWarning("pending")).toBe(true);
    expect(needsLiveRunWarning("failed")).toBe(false);
    expect(needsLiveRunWarning("budget_exhausted")).toBe(false);
  });
});

describe("resumeStrategyErrorMessage", () => {
  it("is plain for a network failure", () => {
    expect(resumeStrategyErrorMessage(new Error("x"))).toMatch(/connection/i);
  });
  it("passes the server's reason for 409 and 422", () => {
    expect(resumeStrategyErrorMessage(new ApiError(409, "already finished")))
      .toBe("already finished");
    expect(resumeStrategyErrorMessage(new ApiError(422, "must exceed $1.00")))
      .toBe("must exceed $1.00");
  });
});
