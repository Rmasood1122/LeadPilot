/** Pure helpers for the Feature Group 3 screens. No React, no fetching —
 *  everything here is unit-tested in tests/revenue.test.ts. */

import type { SentimentWeek } from "./api/revenue";

/** Monday-first, matching the API's dow (Python weekday(): Monday = 0). */
export const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Cents -> "$1,250" / "$12.50". Null renders as an em dash: "no meetings
 *  yet" must never look like "meetings cost nothing". */
export function formatMoney(cents: number | null | undefined, currency = "USD"): string {
  if (cents === null || cents === undefined) return "—";
  const units = cents / 100;
  const whole = Math.abs(units) >= 1000;
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: whole ? 0 : 2,
      maximumFractionDigits: whole ? 0 : 2,
    }).format(units);
  } catch {
    return `${units.toFixed(whole ? 0 : 2)} ${currency}`;
  }
}

/** 1.5 -> "+150%", -0.25 -> "−25%", null -> "—". */
export function formatRoi(roi: number | null | undefined): string {
  if (roi === null || roi === undefined) return "—";
  const pct = Math.round(roi * 100);
  if (pct > 0) return `+${pct}%`;
  if (pct < 0) return `−${Math.abs(pct)}%`;
  return "0%";
}

export type RangePreset = "30d" | "90d" | "12m" | "ytd";

function iso(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Inclusive date range for a preset, ending today. */
export function presetRange(preset: RangePreset, today: Date = new Date()): { from: string; to: string } {
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const start = new Date(end);
  if (preset === "30d") start.setDate(end.getDate() - 29);
  else if (preset === "90d") start.setDate(end.getDate() - 89);
  else if (preset === "12m") {
    start.setFullYear(end.getFullYear() - 1);
    start.setDate(start.getDate() + 1);
  } else {
    start.setMonth(0, 1);
  }
  return { from: iso(start), to: iso(end) };
}

/** "2026-07" -> "Jul 2026". */
export function monthLabel(month: string): string {
  const [y, m] = month.split("-").map(Number);
  if (!y || !m) return month;
  return new Date(y, m - 1, 1).toLocaleString("en-US", { month: "short", year: "numeric" });
}

/** Sequential (single-hue) intensity for a heatmap cell: 0 stays empty, any
 *  non-zero value is at least faintly visible, the max is full strength. */
export function heatAlpha(value: number, max: number): number {
  if (!value || max <= 0) return 0;
  return Math.min(1, 0.12 + 0.88 * (value / max));
}

/** Readable text on a primary-tinted cell of the given alpha. */
export function heatTextClass(alpha: number): string {
  return alpha > 0.55 ? "text-[rgb(var(--primary-foreground))]" : "text-foreground";
}

/** "Tue 9:00–10:00" (lead local time). */
export function formatWindow(dow: number, hour: number): string {
  const pad = (h: number) => `${h % 24}:00`;
  return `${DOW_LABELS[dow] ?? "?"} ${pad(hour)}–${pad(hour + 1)}`;
}

/** Chart rows for the sentiment trend: rates as percentages, null (no
 *  replies that week) kept null so the line breaks instead of dipping to 0. */
export function sentimentChartData(weeks: SentimentWeek[]) {
  return weeks.map((w) => ({
    week: new Date(`${w.week_start}T00:00:00`).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
    weekStart: w.week_start,
    objection: w.objection_rate === null ? null : Math.round(w.objection_rate * 1000) / 10,
    interested: w.interested_rate === null ? null : Math.round(w.interested_rate * 1000) / 10,
    total: w.total,
    partial: w.partial,
    alerted: w.alerted,
  }));
}

/** Week-over-week objection change between the last two COMPLETE weeks,
 *  or null when either has no replies. */
export function objectionChange(weeks: SentimentWeek[]): number | null {
  const complete = weeks.filter((w) => !w.partial);
  if (complete.length < 2) return null;
  const prev = complete[complete.length - 2].objection_rate;
  const cur = complete[complete.length - 1].objection_rate;
  if (prev === null || cur === null) return null;
  return Math.round((cur - prev) * 1000) / 10;
}
