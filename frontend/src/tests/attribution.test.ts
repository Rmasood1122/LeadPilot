import { describe, expect, it } from "vitest";

import {
  certainShare,
  certaintyNote,
  gapLabel,
  methodTone,
  outcomeLabel,
  rankedSteps,
  summaryCaveat,
  touchLabel,
  type AttributionEntry,
  type AttributionSummary,
} from "@/lib/attribution";

function entry(overrides: Partial<AttributionEntry> = {}): AttributionEntry {
  return {
    id: "a1", outcome_kind: "meeting_booked", outcome_at: "2026-09-16T12:00:00Z",
    lead: { id: "l1", full_name: "Sara Khan", company: "Blaze Safety" },
    message_id: "m1", channel: "email", step_no: 2,
    message_sent_at: "2026-09-16T08:00:00Z", hours_to_outcome: 4,
    method: "last_touch", method_label: "Last message sent before the outcome",
    confidence: 0.7, is_certain: false,
    evidence: ["No reply is linked to a message…"],
    subject: "Your inspection backlog", body: "Who owns scheduling?",
    ...overrides,
  };
}

function summary(overrides: Partial<AttributionSummary> = {}): AttributionSummary {
  return {
    total: 10, certain: 6,
    by_step: [{ step_no: 2, count: 6, certain: 4 }, { step_no: 1, count: 4, certain: 2 }],
    by_channel: [{ channel: "email", count: 10, certain: 6 }],
    by_method: [
      { method: "direct_reply", label: "They replied to this message", count: 6 },
      { method: "last_touch", label: "Last message sent before the outcome", count: 4 },
      { method: "thread_match", label: "Their reply is in this message's thread", count: 0 },
      { method: "none", label: "Nothing was sent before this", count: 0 },
    ],
    median_hours_to_outcome: 6,
    ...overrides,
  };
}

describe("labels", () => {
  it("names each outcome kind", () => {
    expect(outcomeLabel("meeting_booked")).toBe("Meeting booked");
    expect(outcomeLabel("won")).toBe("Deal won");
  });

  it("makes a fact and a guess look different", () => {
    expect(methodTone("direct_reply")).toBe("success");
    expect(methodTone("thread_match")).toBe("warning");
    expect(methodTone("last_touch")).toBe("default");
    expect(methodTone("none")).toBe("default");
  });
});

describe("touchLabel", () => {
  it("names the step and the channel", () => {
    expect(touchLabel(entry())).toBe("Step 2 · Email");
  });

  it("says plainly when there is nothing to credit", () => {
    expect(touchLabel(entry({ message_id: null }))).toBe("No touch to credit");
  });

  it("degrades without a step number", () => {
    expect(touchLabel(entry({ step_no: null }))).toBe("Email");
  });

  it("does not invent a channel", () => {
    expect(touchLabel(entry({ channel: null }))).toBe("Step 2 · Unknown channel");
  });
});

describe("gapLabel", () => {
  it("reads naturally at each scale", () => {
    expect(gapLabel(0.4)).toBe("within the hour");
    expect(gapLabel(4)).toBe("4h later");
    expect(gapLabel(120)).toBe("5 days later");
  });

  it("is empty when unknown", () => {
    expect(gapLabel(null)).toBe("");
  });
});

describe("certaintyNote", () => {
  it("says a fact is known", () => {
    expect(certaintyNote(entry({ is_certain: true })))
      .toBe("Known — they replied to this message.");
  });

  it("says a guess is inferred, with the number", () => {
    expect(certaintyNote(entry()))
      .toBe("Inferred (70% confidence) — last message sent before the outcome.");
  });

  it("is honest when nothing was sent", () => {
    expect(certaintyNote(entry({ method: "none", message_id: null })))
      .toBe("Nothing was sent before this outcome.");
  });
});

describe("certainShare", () => {
  it("is the share confirmed by a reply", () => {
    expect(certainShare(summary())).toBeCloseTo(0.6, 5);
  });

  it("is null rather than 0% when there is nothing to divide by", () => {
    expect(certainShare(summary({ total: 0, certain: 0 }))).toBeNull();
    expect(certainShare(null)).toBeNull();
  });
});

describe("summaryCaveat", () => {
  it("is silent when most of the ledger is confirmed", () => {
    expect(summaryCaveat(summary())).toBeNull();
  });

  it("warns when the aggregate is mostly guesswork", () => {
    const text = summaryCaveat(summary({ total: 10, certain: 2 })) as string;
    expect(text).toContain("Only 20%");
    expect(text).toContain("which is a guess");
  });

  it("is silent with no data rather than warning about nothing", () => {
    expect(summaryCaveat(summary({ total: 0, certain: 0 }))).toBeNull();
  });
});

describe("rankedSteps", () => {
  it("puts the step that earned the most first", () => {
    expect(rankedSteps(summary()).map((s) => s.step_no)).toEqual([2, 1]);
  });

  it("breaks a tie by step order, so the list is stable", () => {
    const rows = rankedSteps(summary({
      by_step: [{ step_no: 3, count: 4, certain: 0 }, { step_no: 1, count: 4, certain: 0 }],
    }));
    expect(rows.map((s) => s.step_no)).toEqual([1, 3]);
  });

  it("is empty without data", () => {
    expect(rankedSteps(undefined)).toEqual([]);
  });
});
