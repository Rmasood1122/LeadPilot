import { describe, expect, it } from "vitest";
import {
  buildStartBody,
  dayLabel,
  endReasonLabel,
  formatActual,
  formatTarget,
  initialForm,
  isDisabledError,
  pilotExportFilename,
  pilotDates,
  pilotExportPath,
  statusLabel,
  statusTone,
  unitsToCents,
  utcStamp,
  verdictHeadline,
  type PilotTemplate,
} from "@/lib/pilot";

const template: PilotTemplate = {
  pilot_days: 30,
  scorecard_after_days: [7, 14, 21, 28],
  billing_statement: "The pilot did not change your plan or billing.",
  criteria: [
    { key: "meetings_booked_min", label: "Meetings booked", kind: "min", unit: "count",
      min_value: 1, max_value: 100_000, default_selected: true },
    { key: "meetings_held_min", label: "Meetings held", kind: "min", unit: "count",
      min_value: 1, max_value: 100_000, default_selected: false },
    { key: "max_cost_per_meeting_booked_cents", label: "Cost per booked meeting", kind: "max",
      unit: "money", min_value: 1, max_value: 100_000_000, default_selected: true },
  ],
};

const opts = { strategyIds: null, scorecardEmails: true };

describe("setup form", () => {
  it("ticks the template defaults and pre-fills no target", () => {
    const form = initialForm(template);
    expect(form.meetings_booked_min).toEqual({ selected: true, value: "" });
    expect(form.meetings_held_min).toEqual({ selected: false, value: "" });
    expect(Object.values(form).every((c) => c.value === "")).toBe(true);
  });

  it("converts currency units to whole cents", () => {
    expect(unitsToCents("250")).toBe(25_000);
    expect(unitsToCents("249.99")).toBe(24_999);
    expect(unitsToCents("1,200.5")).toBe(120_050);
    expect(unitsToCents("0.1")).toBe(10);
    expect(unitsToCents("12.345")).toBeNull();
    expect(unitsToCents("-5")).toBeNull();
    expect(unitsToCents("abc")).toBeNull();
  });

  it("builds the body from ticked criteria only", () => {
    const form = initialForm(template);
    form.meetings_booked_min.value = "5";
    form.max_cost_per_meeting_booked_cents.value = "300";
    form.meetings_held_min.value = "9";        // not ticked -> ignored
    expect(buildStartBody(template, form, opts)).toEqual({
      body: {
        criteria: { meetings_booked_min: 5, max_cost_per_meeting_booked_cents: 30_000 },
        strategy_ids: null,
        scorecard_emails: true,
      },
    });
  });

  it("refuses what the server would refuse, with a message", () => {
    const form = initialForm(template);
    expect(buildStartBody(template, form, opts)).toEqual({ error: "Meetings booked: enter a target." });
    form.meetings_booked_min.value = "2.5";
    expect(buildStartBody(template, form, opts)).toEqual({ error: "Meetings booked: enter a whole number." });
    form.meetings_booked_min.value = "0";
    expect(buildStartBody(template, form, opts)).toEqual({
      error: "Meetings booked: the target must be at least 1.",
    });
    form.meetings_booked_min.value = "100001";
    expect(buildStartBody(template, form, opts)).toEqual({ error: "Meetings booked: the target is too large." });
    form.meetings_booked_min.value = "3";
    form.max_cost_per_meeting_booked_cents.value = "ten";
    expect("error" in buildStartBody(template, form, opts)).toBe(true);
    form.max_cost_per_meeting_booked_cents.value = "0";
    expect(buildStartBody(template, form, opts)).toEqual({
      error: "Cost per booked meeting: the target must be at least 1.",
    });
  });

  it("needs at least one criterion and at least one chosen campaign", () => {
    const none = initialForm(template);
    for (const key of Object.keys(none)) none[key].selected = false;
    expect(buildStartBody(template, none, opts)).toEqual({ error: "Set at least one success criterion." });
    const form = initialForm(template);
    form.meetings_booked_min.value = "1";
    form.max_cost_per_meeting_booked_cents.selected = false;
    expect("error" in buildStartBody(template, form, { strategyIds: [], scorecardEmails: false })).toBe(true);
    expect(buildStartBody(template, form, { strategyIds: ["s1"], scorecardEmails: false })).toEqual({
      body: { criteria: { meetings_booked_min: 1 }, strategy_ids: ["s1"], scorecard_emails: false },
    });
  });
});

describe("verdict wording", () => {
  const money = (cents: number) => `$${(cents / 100).toFixed(2)}`;

  it("formats targets and actuals", () => {
    expect(formatTarget({ kind: "min", unit: "count", target: 5 }, money)).toBe("at least 5");
    expect(formatTarget({ kind: "max", unit: "money", target: 30_000 }, money)).toBe("at most $300.00");
    expect(formatActual({ unit: "money", actual: 5_000 }, money)).toBe("$50.00");
    expect(formatActual({ unit: "money", actual: null }, money)).toBe("—");
    expect(formatActual({ unit: "count", actual: 0 }, money)).toBe("0");
  });

  it("says 'so far' while running and is final on the verdict", () => {
    expect(statusLabel("met", false)).toBe("Met so far");
    expect(statusLabel("not_met", false)).toBe("Not yet");
    expect(statusLabel("met", true)).toBe("Met");
    expect(statusLabel("not_met", true)).toBe("Not met");
    expect(statusLabel("not_comparable", true)).toBe("Not comparable");
    expect([statusTone("met"), statusTone("not_met"), statusTone("not_comparable")])
      .toEqual(["good", "bad", "neutral"]);
  });

  it("headlines the outcome with the count", () => {
    expect(verdictHeadline({ met_count: 3, criteria_count: 3, outcome: "met" }))
      .toBe("Every criterion met — 3 of 3 criteria met.");
    expect(verdictHeadline({ met_count: 2, criteria_count: 3, outcome: "not_met" }))
      .toBe("Not every criterion met — 2 of 3 criteria met.");
  });

  it("labels the day and how the pilot ended", () => {
    expect(dayLabel({ status: "active", day: 8, pilot_days: 30 })).toBe("Day 8 of 30");
    expect(dayLabel({ status: "ended", day: null, pilot_days: 30 })).toBe("Ended");
    expect(dayLabel({ status: "active", day: 30, pilot_days: 30, phase: "verdict_pending",
                      verdict_final_at: "2026-10-02T00:00:00+00:00" }))
      .toBe("Verdict pending — final numbers at 2026-10-02 00:00 UTC");
    expect(dayLabel({ status: "active", day: 12, pilot_days: 30, phase: "active",
                      verdict_final_at: "2026-10-02T00:00:00+00:00" })).toBe("Day 12 of 30");
    expect(utcStamp("not a date")).toBe("not a date");
    expect(endReasonLabel("completed")).toBe("Completed 30 days");
    expect(endReasonLabel("ended_early")).toBe("Ended early");
  });
});

describe("pilot dates", () => {
  it("uses UTC calendar days: day 1 is today's UTC date, day 30 is 29 days later", () => {
    expect(pilotDates(new Date("2026-09-01T09:00:00Z"))).toEqual({ start: "2026-09-01", end: "2026-09-30" });
    // 23:59 UTC still counts as day 1 (the short-day-1 case the form warns about).
    expect(pilotDates(new Date("2026-09-01T23:59:00Z"))).toEqual({ start: "2026-09-01", end: "2026-09-30" });
    expect(pilotDates(new Date("2026-02-15T00:00:00Z"))).toEqual({ start: "2026-02-15", end: "2026-03-16" });
  });
});

describe("export and errors", () => {
  it("builds the export path and filename like the API", () => {
    expect(pilotExportPath("p1", "pdf")).toBe("/pilots/p1/export?format=pdf");
    expect(pilotExportPath("p1", "pdf", "campaigns")).toBe("/pilots/p1/export?format=pdf");
    expect(pilotExportPath("p1", "csv", "campaigns")).toBe("/pilots/p1/export?format=csv&view=campaigns");
    expect(pilotExportFilename("2026-09-01", "pdf")).toBe("leadpilot-pilot-verdict-2026-09-01.pdf");
    expect(pilotExportFilename("2026-09-01", "csv", "campaigns"))
      .toBe("leadpilot-pilot-verdict-2026-09-01-campaigns.csv");
  });

  it("treats only the flag-off 409 as 'disabled'", () => {
    expect(isDisabledError({ status: 409, detail: "Pilot mode is disabled by the administrator" })).toBe(true);
    expect(isDisabledError({ status: 409, detail: "A pilot is already running for this account." })).toBe(false);
    expect(isDisabledError({ status: 404, detail: "pilot not found" })).toBe(false);
    expect(isDisabledError(null)).toBe(false);
  });
});
