/**
 * Product defect #21: the campaign banner said "≥ 3%" although the pause fires
 * when the bounce rate is ABOVE the threshold, and a workspace compliance rule
 * can lower that threshold (the API now reports the one in force).
 */
import { describe, expect, it } from "vitest";
import { bounceOverThreshold, bouncePauseText } from "@/lib/campaignBounce";

describe("campaign bounce text", () => {
  it("uses the threshold the server reports, with 'above'", () => {
    expect(bouncePauseText({ bounce_rate: 0.025, bounce_pause_threshold: 0.02 }))
      .toBe("Bounce rate auto-pause: 2.5% is above the 2% limit. Fix deliverability issues, then resume.");
  });
  it("falls back to the standard 3% when an older server sends no threshold", () => {
    expect(bouncePauseText({ bounce_rate: 0.04 })).toContain("above the 3% limit");
  });
  it("is over only when strictly above, like the pause", () => {
    expect(bounceOverThreshold({ bounce_rate: 0.03, bounce_pause_threshold: 0.03 })).toBe(false);
    expect(bounceOverThreshold({ bounce_rate: 0.031, bounce_pause_threshold: 0.03 })).toBe(true);
    expect(bounceOverThreshold({ bounce_rate: 0.021, bounce_pause_threshold: 0.02 })).toBe(true);
  });
});
