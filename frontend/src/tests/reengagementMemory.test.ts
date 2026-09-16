import { describe, expect, it } from "vitest";

import type { ReengagementPlan } from "@/lib/api/reengagement";
import {
  MIN_CANCEL_REASON,
  cancelReasonError,
  dueLabel,
  isDue,
  reasonTone,
  sortPlans,
  statusTone,
  suggestedOpener,
  whyThisDate,
} from "@/lib/reengagementMemory";

const NOW = new Date("2026-09-16T12:00:00Z");

function plan(overrides: Partial<ReengagementPlan> = {}): ReengagementPlan {
  return {
    id: "p1",
    lead: { id: "l1", full_name: "Sara Khan", company: "Blaze Safety",
            email: "sara@blaze.test", status: "contacted" },
    reason_kind: "budget", reason_label: "No budget right now",
    reason_text: "no budget until the new fiscal year",
    date_from_prospect: false, stated_return_on: null,
    due_at: "2026-12-15T00:00:00Z", interval_days: 90, status: "scheduled",
    message_id: null, outcome: null, cancelled_reason: null,
    created_at: "2026-09-16T10:00:00Z",
    ...overrides,
  };
}

describe("dueLabel", () => {
  it("counts forward, and names today and tomorrow", () => {
    expect(dueLabel(plan({ due_at: "2026-09-16T00:00:00Z" }), NOW)).toBe("today");
    expect(dueLabel(plan({ due_at: "2026-09-17T12:00:00Z" }), NOW)).toBe("tomorrow");
    expect(dueLabel(plan({ due_at: "2026-09-28T12:00:00Z" }), NOW)).toBe("in 12 days");
  });

  it("counts overdue, because a promise nobody sees aging is a promise nobody keeps", () => {
    expect(dueLabel(plan({ due_at: "2026-09-15T12:00:00Z" }), NOW)).toBe("1 day overdue");
    expect(dueLabel(plan({ due_at: "2026-09-13T12:00:00Z" }), NOW)).toBe("3 days overdue");
  });

  it("is empty without a date", () => {
    expect(dueLabel(plan({ due_at: null }), NOW)).toBe("");
  });
});

describe("isDue", () => {
  it("is true once the date has passed", () => {
    expect(isDue(plan({ due_at: "2026-09-15T00:00:00Z" }), NOW)).toBe(true);
    expect(isDue(plan(), NOW)).toBe(false);
  });

  it("is never true for a finished plan", () => {
    expect(isDue(plan({ due_at: "2020-01-01T00:00:00Z", status: "sent" }), NOW))
      .toBe(false);
    expect(isDue(plan({ due_at: "2020-01-01T00:00:00Z", status: "cancelled" }), NOW))
      .toBe(false);
  });
});

describe("whyThisDate", () => {
  it("says so when the prospect named the date", () => {
    expect(whyThisDate(plan({ date_from_prospect: true,
                              stated_return_on: "2027-03-01" })))
      .toBe("They asked us to come back on 2027-03-01.");
  });

  it("explains the default, and which reason it came from", () => {
    expect(whyThisDate(plan()))
      .toBe('No date given — 90 days from their reply, the usual wait for '
        + '"no budget right now".');
  });

  it("degrades without an interval", () => {
    expect(whyThisDate(plan({ interval_days: null }))).toBe("No date given.");
  });
});

describe("suggestedOpener", () => {
  it("quotes them and uses their first name", () => {
    expect(suggestedOpener(plan()))
      .toBe("Hi Sara — when we spoke you said no budget until the new fiscal year. "
        + "Has that changed?");
  });

  it("still opens honestly when they gave no reason", () => {
    expect(suggestedOpener(plan({ reason_text: null })))
      .toBe("Hi Sara — you asked me to come back around now. Is this a better time?");
  });

  it("does not break without a name", () => {
    expect(suggestedOpener(plan({ lead: null }))).toContain("Hi there");
  });
});

describe("tones", () => {
  it("marks the longest wait most strongly", () => {
    expect(reasonTone("contract")).toBe("destructive");
    expect(reasonTone("budget")).toBe("warning");
    expect(reasonTone("timing")).toBe("default");
    expect(reasonTone(null)).toBe("default");
  });

  it("tones each status", () => {
    expect(statusTone("sent")).toBe("success");
    expect(statusTone("due")).toBe("warning");
    expect(statusTone("cancelled")).toBe("destructive");
    expect(statusTone("scheduled")).toBe("default");
  });
});

describe("sortPlans", () => {
  it("puts overdue promises first, then soonest", () => {
    const rows = [
      plan({ id: "later", due_at: "2027-01-01T00:00:00Z" }),
      plan({ id: "overdue", due_at: "2026-09-01T00:00:00Z" }),
      plan({ id: "soon", due_at: "2026-10-01T00:00:00Z" }),
    ];
    expect(sortPlans(rows, NOW).map((p) => p.id)).toEqual(["overdue", "soon", "later"]);
  });

  it("does not mutate its input", () => {
    const rows = [plan({ id: "a", due_at: "2027-01-01T00:00:00Z" }),
                  plan({ id: "b", due_at: "2026-09-01T00:00:00Z" })];
    sortPlans(rows, NOW);
    expect(rows[0].id).toBe("a");
  });
});

describe("cancelReasonError", () => {
  it("refuses a shrug", () => {
    expect(cancelReasonError("x")).toContain(String(MIN_CANCEL_REASON));
    expect(cancelReasonError("   ")).not.toBeNull();
  });

  it("accepts a real reason", () => {
    expect(cancelReasonError("They went with a competitor")).toBeNull();
  });
});
