import { describe, expect, it } from "vitest";

import {
  DIFFICULTIES,
  canBeScored,
  difficultyNote,
  emptyScript,
  historyHeadline,
  improvement,
  isNearlyOver,
  isSuggested,
  readinessTone,
  scoreRows,
  scoreTone,
  scriptGaps,
  scriptSummary,
  sortedItems,
  turnBudget,
  type CallScript,
  type PracticeHistory,
  type Readiness,
  type RoleplaySession,
  type ScriptResponse,
} from "@/lib/practice";

function script(overrides: Partial<CallScript> = {}): CallScript {
  return {
    opening: "Thanks for booking, Sara.",
    discovery: ["Who owns scheduling?", "What happens when one is missed?"],
    objections: [
      { objection: "We use a spreadsheet", response: "Ask what a miss costs." },
      { objection: "No budget", response: "Ask when the cycle resets." },
      { objection: "We looked before", response: "Ask what stopped it." },
    ],
    close: "Shall we book thirty minutes?",
    notes: "",
    ...overrides,
  };
}

function readiness(overrides: Partial<Readiness> = {}): Readiness {
  return {
    brief_id: "b1", lead_id: "l1",
    items: [
      { key: "brief", label: "Prep brief generated", done: true,
        detail: "Ready to read.", blocking: false },
      { key: "script", label: "Call script reviewed", done: false,
        detail: "Still the draft.", blocking: false },
      { key: "objections", label: "Objections prepared", done: true,
        detail: "3 ready.", blocking: false },
      { key: "practice", label: "Practised the call", done: false,
        detail: "Not rehearsed yet.", blocking: false },
    ],
    done: 2, total: 4, ready: true, blocking: [], practice_required: false,
    meeting_start_at: "2026-09-16T15:00:00Z", minutes_until: 180,
    headline: "Ready — in 3 hours, but 2 things still open.",
    ...overrides,
  };
}

function session(overrides: Partial<RoleplaySession> = {}): RoleplaySession {
  return {
    id: "s1", status: "active", difficulty: "realistic",
    lead: { id: "l1", full_name: "Sara Khan", company: "Blaze Safety" },
    brief_id: "b1", persona: null,
    objectives: ["Open in under 60 seconds without pitching."],
    turn_count: 6, max_turns: 40,
    scores: { overall: null, discovery: null, objections: null, tone: null, close: null },
    feedback: null, error: null,
    started_at: "2026-09-16T12:00:00Z", ended_at: null,
    turns: [
      { turn_no: 1, role: "prospect", content: "Hi — Sara here.", at: null },
      { turn_no: 2, role: "seller", content: "Thanks for the time.", at: null },
      { turn_no: 3, role: "prospect", content: "What is this about?", at: null },
      { turn_no: 4, role: "seller", content: "You mentioned inspections.", at: null },
    ],
    ...overrides,
  };
}

describe("emptyScript", () => {
  it("has every field, so components need no guards", () => {
    expect(Object.keys(emptyScript()).sort())
      .toEqual(["close", "discovery", "notes", "objections", "opening"]);
  });
});

describe("isSuggested", () => {
  it("is true until a person has touched it", () => {
    const base: ScriptResponse = { brief_id: "b1", script: script(), edited: false,
                                   edited_at: null, edited_by_user_id: null };
    expect(isSuggested(base)).toBe(true);
    expect(isSuggested({ ...base, edited: true })).toBe(false);
  });

  it("treats missing data as suggested rather than approved", () => {
    expect(isSuggested(null)).toBe(true);
  });
});

describe("scriptSummary", () => {
  it("says what the seller is walking in with", () => {
    expect(scriptSummary(script()))
      .toBe("opening ready · 2 questions · 3 objections · close ready");
  });

  it("names what is missing rather than counting it as present", () => {
    expect(scriptSummary(script({ opening: "  ", close: "" })))
      .toContain("no opening");
    expect(scriptSummary(script({ opening: "  ", close: "" }))).toContain("no close");
  });

  it("ignores blank rows when counting", () => {
    expect(scriptSummary(script({ discovery: ["", "  ", "real one"] })))
      .toContain("1 question");
  });
});

describe("scriptGaps", () => {
  it("is empty for a complete script", () => {
    expect(scriptGaps(script())).toEqual([]);
  });

  it("asks for three objections, not one", () => {
    expect(scriptGaps(script({ objections: [{ objection: "cost", response: "" }] })))
      .toContain("at least three objections");
  });

  it("names every blank part", () => {
    expect(scriptGaps(emptyScript()))
      .toEqual(["opening", "discovery questions", "at least three objections", "close"]);
  });
});

describe("readiness", () => {
  it("is destructive while something blocks", () => {
    expect(readinessTone(readiness({ ready: false }))).toBe("destructive");
  });

  it("is a warning while optional things are open, and success when done", () => {
    expect(readinessTone(readiness())).toBe("warning");
    expect(readinessTone(readiness({ done: 4 }))).toBe("success");
  });

  it("puts blocking items first, then the undone ones", () => {
    const state = readiness({
      items: [
        { key: "a", label: "A", done: true, detail: "", blocking: false },
        { key: "b", label: "B", done: false, detail: "", blocking: false },
        { key: "c", label: "C", done: false, detail: "", blocking: true },
      ],
    });
    expect(sortedItems(state).map((i) => i.key)).toEqual(["c", "b", "a"]);
  });

  it("is empty without data rather than throwing", () => {
    expect(sortedItems(null)).toEqual([]);
    expect(readinessTone(undefined)).toBe("default");
  });
});

describe("difficulty", () => {
  it("describes each level so the choice is informed", () => {
    expect(DIFFICULTIES).toHaveLength(3);
    expect(difficultyNote("hostile")).toContain("end the call");
    expect(difficultyNote("easy")).toContain("gives ground");
  });
});

describe("turn budget", () => {
  it("says how much rehearsal is left", () => {
    expect(turnBudget(session())).toBe("6 of 40 turns");
    expect(turnBudget(null)).toBe("");
  });

  it("warns near the end so the seller starts closing", () => {
    expect(isNearlyOver(session())).toBe(false);
    expect(isNearlyOver(session({ turn_count: 37 }))).toBe(true);
  });
});

describe("canBeScored", () => {
  it("needs two of the seller's own lines", () => {
    expect(canBeScored(session())).toBe(true);
    expect(canBeScored(session({
      turns: [{ turn_no: 1, role: "prospect", content: "hi", at: null },
              { turn_no: 2, role: "seller", content: "hello", at: null }],
    }))).toBe(false);
  });

  it("is false with no transcript at all", () => {
    expect(canBeScored(session({ turns: [] }))).toBe(false);
    expect(canBeScored(null)).toBe(false);
  });
});

describe("scoreRows", () => {
  it("returns the five in a fixed order", () => {
    const rows = scoreRows({ overall: 72, discovery: 80, objections: 55, tone: 78,
                             close: 60 });
    expect(rows.map((r) => r.key))
      .toEqual(["overall", "discovery", "objections", "tone", "close"]);
  });

  it("skips a score the coach did not give rather than showing zero", () => {
    const rows = scoreRows({ overall: 70, discovery: null, objections: null,
                             tone: null, close: null });
    expect(rows.map((r) => r.key)).toEqual(["overall"]);
  });

  it("is empty without scores", () => {
    expect(scoreRows(null)).toEqual([]);
  });
});

describe("scoreTone", () => {
  it("bands the score", () => {
    expect(scoreTone(90)).toBe("success");
    expect(scoreTone(60)).toBe("warning");
    expect(scoreTone(30)).toBe("destructive");
    expect(scoreTone(null)).toBe("default");
  });
});

describe("history", () => {
  function history(overrides: Partial<PracticeHistory> = {}): PracticeHistory {
    return {
      total: 3, completed: 3, items: [],
      trend: [
        { at: "2026-09-01T00:00:00Z", overall: 40, discovery: 40, objections: 40,
          tone: 40, close: 40 },
        { at: "2026-09-08T00:00:00Z", overall: 60, discovery: 60, objections: 60,
          tone: 60, close: 60 },
        { at: "2026-09-15T00:00:00Z", overall: 80, discovery: 80, objections: 80,
          tone: 80, close: 80 },
      ],
      average_overall: 60, best_overall: 80,
      ...overrides,
    };
  }

  it("measures improvement from the first scored session", () => {
    expect(improvement(history())).toBe(40);
  });

  it("claims no improvement from a single session", () => {
    expect(improvement(history({ trend: history().trend.slice(0, 1) }))).toBeNull();
    expect(improvement(null)).toBeNull();
  });

  it("says there is no practice yet rather than reporting a zero", () => {
    expect(historyHeadline(history({ total: 0, completed: 0, trend: [],
                                     average_overall: null })))
      .toBe("No practice sessions yet.");
  });

  it("distinguishes unscored sessions from bad ones", () => {
    expect(historyHeadline(history({ average_overall: null, trend: [] })))
      .toBe("3 sessions, none scored yet.");
  });

  it("reports the trend direction in words", () => {
    expect(historyHeadline(history())).toContain("up 40 points since your first");
    const falling = history().trend.slice().reverse();
    expect(historyHeadline(history({ trend: falling })))
      .toContain("down 40 points since your first");
  });
});
