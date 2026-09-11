import { describe, expect, it } from "vitest";
import {
  formatMoney,
  formatRoi,
  formatWindow,
  heatAlpha,
  heatTextClass,
  monthLabel,
  objectionChange,
  presetRange,
  sentimentChartData,
} from "@/lib/revenue";
import type { SentimentWeek } from "@/lib/api/revenue";

function week(start: string, total: number, objection: number, extra: Partial<SentimentWeek> = {}): SentimentWeek {
  return {
    week_start: start, total, interested: 0, question: 0, objection, not_interested: 0,
    unsubscribe: 0, objection_rate: total ? objection / total : null,
    interested_rate: total ? 0 : null, alerted: false, partial: false, ...extra,
  };
}

describe("formatMoney", () => {
  it("formats cents with the right precision", () => {
    expect(formatMoney(1250, "USD")).toBe("$12.50");
    expect(formatMoney(125_000, "USD")).toBe("$1,250");
  });
  it("renders null as an em dash, never as zero", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(0)).toBe("$0.00");
  });
  it("survives an unknown currency code", () => {
    expect(formatMoney(500, "ZZZ")).toMatch(/5/);
  });
});

describe("formatRoi", () => {
  it("signs the percentage", () => {
    expect(formatRoi(1.5)).toBe("+150%");
    expect(formatRoi(-0.25)).toBe("−25%");
    expect(formatRoi(0)).toBe("0%");
    expect(formatRoi(null)).toBe("—");
  });
});

describe("presetRange", () => {
  const today = new Date(2026, 8, 11); // 11 Sep 2026
  it("counts inclusive days", () => {
    expect(presetRange("30d", today)).toEqual({ from: "2026-08-13", to: "2026-09-11" });
    expect(presetRange("90d", today)).toEqual({ from: "2026-06-14", to: "2026-09-11" });
  });
  it("covers year to date and twelve months", () => {
    expect(presetRange("ytd", today)).toEqual({ from: "2026-01-01", to: "2026-09-11" });
    expect(presetRange("12m", today)).toEqual({ from: "2025-09-12", to: "2026-09-11" });
  });
});

describe("heatmap helpers", () => {
  it("keeps zero empty and scales up to full strength", () => {
    expect(heatAlpha(0, 10)).toBe(0);
    expect(heatAlpha(5, 0)).toBe(0);
    expect(heatAlpha(10, 10)).toBe(1);
    expect(heatAlpha(1, 100)).toBeGreaterThan(0.1);
  });
  it("switches to readable text on dark cells", () => {
    expect(heatTextClass(0.9)).toContain("primary-foreground");
    expect(heatTextClass(0.2)).toBe("text-foreground");
  });
  it("labels windows Monday-first", () => {
    expect(formatWindow(1, 9)).toBe("Tue 9:00–10:00");
    expect(formatWindow(6, 23)).toBe("Sun 23:00–0:00");
  });
  it("labels months", () => {
    expect(monthLabel("2026-07")).toBe("Jul 2026");
  });
});

describe("sentiment", () => {
  it("keeps weeks without replies as gaps, not zeros", () => {
    const rows = sentimentChartData([week("2026-08-24", 10, 2), week("2026-08-31", 0, 0)]);
    expect(rows[0].objection).toBe(20);
    expect(rows[1].objection).toBeNull();
  });
  it("compares the last two complete weeks only", () => {
    const weeks = [week("2026-08-24", 10, 1), week("2026-08-31", 10, 3),
                   week("2026-09-07", 2, 2, { partial: true })];
    expect(objectionChange(weeks)).toBe(20);
    expect(objectionChange([week("2026-08-31", 0, 0), week("2026-09-07", 4, 1)])).toBeNull();
  });
});
