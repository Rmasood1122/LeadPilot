import { describe, expect, it } from "vitest";
import { expiresInText, formatAmount, readToken, stageScale, weeklyMeetings } from "@/lib/shareLinks";

describe("formatAmount", () => {
  it("formats decimal strings from the API", () => {
    expect(formatAmount("4000.00")).toBe("$4,000");
    expect(formatAmount("1250.50")).toBe("$1,250.50");
    expect(formatAmount(0)).toBe("$0");
  });
  it("survives an unknown currency", () => {
    expect(formatAmount("5", "ZZZ")).toMatch(/5/);
  });
});

describe("expiresInText", () => {
  const now = new Date("2026-09-13T12:00:00Z");
  it("uses hours near the end and days before", () => {
    expect(expiresInText("2026-09-13T17:00:00Z", now)).toBe("in 5 hours");
    expect(expiresInText("2026-09-13T12:30:00Z", now)).toBe("in 1 hour");
    expect(expiresInText("2026-09-20T12:00:00Z", now)).toBe("in 7 days");
    expect(expiresInText("2026-09-12T12:00:00Z", now)).toBe("expired");
  });
});

describe("weeklyMeetings", () => {
  it("sums days into Monday-start weeks", () => {
    const trend = [
      { date: "2026-09-07", meetings_booked: 1, pipeline_value: "0", revenue_attributed: "0" },  // Mon
      { date: "2026-09-13", meetings_booked: 2, pipeline_value: "0", revenue_attributed: "0" },  // Sun
      { date: "2026-09-14", meetings_booked: 4, pipeline_value: "0", revenue_attributed: "0" },  // Mon
      { date: "not-a-date", meetings_booked: 9, pipeline_value: "0", revenue_attributed: "0" },
    ];
    expect(weeklyMeetings(trend)).toEqual([{ week: "2026-09-07", meetings: 3 },
                                           { week: "2026-09-14", meetings: 4 }]);
  });
});

describe("misc", () => {
  it("never scales bars by zero", () => {
    expect(stageScale([])).toBe(1);
    expect(stageScale([{ key: "a", label: "A", count: 7 }])).toBe(7);
  });
  it("reads only plausible tokens", () => {
    expect(readToken("?token=abcdefghijklmnopqrstuvwxyz")).toBe("abcdefghijklmnopqrstuvwxyz");
    expect(readToken("?token=short")).toBeNull();
    expect(readToken("")).toBeNull();
  });
});
