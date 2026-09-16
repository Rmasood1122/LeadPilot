import { describe, expect, it } from "vitest";

import {
  completionCaption,
  groupedReasons,
  guaranteeWarning,
  percent,
  worstSequences,
  type CompletionMetrics,
} from "@/lib/sequenceCompletion";

function metrics(overrides: Partial<CompletionMetrics> = {}): CompletionMetrics {
  return {
    enrolled: 10, running: 2, completed: 5, dropped: 3, unknown: 0, finished: 8,
    completion_rate: 0.625, dropped_unauthorised: 1,
    reasons: [
      { category: "replied", label: "Prospect replied", count: 2, authorised: true },
      { category: "system_kill", label: "Stopped by an automated kill signal",
        count: 1, authorised: false },
    ],
    ...overrides,
  };
}

describe("percent", () => {
  it("shows an em dash rather than 0% when nothing has finished", () => {
    expect(percent(null)).toBe("—");
    expect(percent(0.625)).toBe("63%");
  });
});

describe("completionCaption", () => {
  it("says when nobody is enrolled", () => {
    expect(completionCaption(metrics({ enrolled: 0 }))).toBe("Nobody enrolled yet.");
  });

  it("distinguishes 'still running' from 'failed to complete'", () => {
    expect(completionCaption(metrics({ finished: 0, running: 6 })))
      .toBe("6 still running — nothing has finished yet.");
  });

  it("names the untracked history rather than hiding it", () => {
    expect(completionCaption(metrics({ unknown: 4 })))
      .toContain("4 enrolled before this was tracked");
  });

  it("reports completed out of finished, not out of enrolled", () => {
    expect(completionCaption(metrics())).toContain("5 of 8 finished sequences");
  });
});

describe("guaranteeWarning", () => {
  it("is silent when every early stop was a decision", () => {
    expect(guaranteeWarning(metrics({ dropped_unauthorised: 0 }))).toBeNull();
    expect(guaranteeWarning(null)).toBeNull();
  });

  it("names the count and asks for action", () => {
    expect(guaranteeWarning(metrics({ dropped_unauthorised: 3 })))
      .toBe("3 prospects stopped early without a decision behind them. "
        + "Open the list and find out why.");
  });

  it("uses the singular for one", () => {
    expect(guaranteeWarning(metrics({ dropped_unauthorised: 1 })))
      .toContain("1 prospect stopped early without a decision behind it.");
  });
});

describe("groupedReasons", () => {
  it("splits decisions from drops", () => {
    const { decisions, drops } = groupedReasons(metrics());
    expect(decisions.map((r) => r.category)).toEqual(["replied"]);
    expect(drops.map((r) => r.category)).toEqual(["system_kill"]);
  });

  it("puts the biggest cause first in each group", () => {
    const { decisions } = groupedReasons(metrics({
      reasons: [
        { category: "replied", label: "Prospect replied", count: 2, authorised: true },
        { category: "bounced", label: "Bounced", count: 9, authorised: true },
      ],
    }));
    expect(decisions.map((r) => r.category)).toEqual(["bounced", "replied"]);
  });

  it("is empty without data", () => {
    expect(groupedReasons(undefined)).toEqual({ decisions: [], drops: [] });
  });
});

describe("worstSequences", () => {
  const rows = [
    { ...metrics({ completion_rate: 0.9, finished: 10 }), sequence_id: "a", name: "A" },
    { ...metrics({ completion_rate: 0.2, finished: 4 }), sequence_id: "b", name: "B" },
    { ...metrics({ completion_rate: null, finished: 0 }), sequence_id: "c", name: "C" },
    { ...metrics({ completion_rate: 0.2, finished: 40 }), sequence_id: "d", name: "D" },
  ];

  it("puts the worst first", () => {
    expect(worstSequences(rows).map((r) => r.name)[0]).toBe("D");
  });

  it("breaks a tie by volume, so the bigger problem ranks higher", () => {
    expect(worstSequences(rows).map((r) => r.name).slice(0, 2)).toEqual(["D", "B"]);
  });

  it("excludes sequences with nothing finished — they have no rate to judge", () => {
    expect(worstSequences(rows).map((r) => r.name)).not.toContain("C");
  });

  it("respects the limit", () => {
    expect(worstSequences(rows, 1)).toHaveLength(1);
  });
});
