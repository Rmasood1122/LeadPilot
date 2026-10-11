/** Review L5: the analytics time series is limited to the plan's
 *  analytics_history_days (product defect #18); the chart says so. */
import { describe, expect, it } from "vitest";
import { historyLabel } from "@/lib/analyticsHistory";

describe("historyLabel", () => {
  it("names the window the server applied", () => {
    expect(historyLabel(30)).toBe("last 30 days");
    expect(historyLabel(1)).toBe("last 1 day");
  });
  it("says all history when the plan has no window", () => {
    expect(historyLabel(null)).toBe("all history");
  });
  it("says nothing when an older server does not report it", () => {
    expect(historyLabel(undefined)).toBeNull();
  });
});
