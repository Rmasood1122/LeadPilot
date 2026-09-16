import { describe, expect, it } from "vitest";

import {
  breakdownRows,
  intentExplanation,
  intentLabel,
  intentTone,
  percent,
  qualityCaption,
  qualityIsProvisional,
  type ReplyQuality,
} from "@/lib/replyIntent";

function quality(overrides: Partial<ReplyQuality> = {}): ReplyQuality {
  return {
    sent: 100,
    replies: 20,
    human_replies: 18,
    classified: 18,
    unclassified: 0,
    reply_rate: 0.2,
    positive_reply_rate: 0.06,
    positive_share: 0.3333,
    breakdown: { interested: 6, neutral: 4, objection: 5, not_now: 3, unsubscribe: 0 },
    ...overrides,
  };
}

describe("labels", () => {
  it("names each label", () => {
    expect(intentLabel("interested")).toBe("Interested");
    expect(intentLabel("not_now")).toBe("Not now");
  });

  it("says 'not classified' rather than inventing a label", () => {
    expect(intentLabel(null)).toBe("Not classified");
    expect(intentLabel(undefined)).toBe("Not classified");
  });

  it("tones an objection and an unsubscribe as bad news", () => {
    expect(intentTone("interested")).toBe("success");
    expect(intentTone("not_now")).toBe("warning");
    expect(intentTone("objection")).toBe("destructive");
    expect(intentTone("unsubscribe")).toBe("destructive");
    expect(intentTone(null)).toBe("default");
  });
});

describe("percent", () => {
  it("rounds to whole percent", () => {
    expect(percent(0.735)).toBe("74%");
    expect(percent(0)).toBe("0%");
  });

  it("shows an em dash for a missing rate, never 0%", () => {
    expect(percent(null)).toBe("—");
    expect(percent(undefined)).toBe("—");
  });
});

describe("qualityCaption", () => {
  it("says nothing has been sent", () => {
    expect(qualityCaption(quality({ sent: 0 }))).toBe("Nothing sent yet.");
  });

  it("separates 'no human replies' from 'no replies'", () => {
    expect(qualityCaption(quality({ human_replies: 0, replies: 4 })))
      .toBe("4 replies, none from a person yet.");
  });

  it("reports the unclassified backlog", () => {
    expect(qualityCaption(quality({ classified: 10, unclassified: 8 })))
      .toContain("8 still to classify");
  });

  it("is quiet once everything is classified", () => {
    expect(qualityCaption(quality())).toBe("18 human replies classified");
  });

  it("uses the singular for one reply", () => {
    expect(qualityCaption(quality({ human_replies: 1, classified: 1 })))
      .toBe("1 human reply classified");
  });
});

describe("qualityIsProvisional", () => {
  it("is provisional with no rate at all", () => {
    expect(qualityIsProvisional(quality({ positive_reply_rate: null }))).toBe(true);
    expect(qualityIsProvisional(null)).toBe(true);
  });

  it("is provisional on a handful of replies", () => {
    expect(qualityIsProvisional(quality({ human_replies: 4, classified: 4 }))).toBe(true);
  });

  it("is provisional when most replies carry no label", () => {
    expect(qualityIsProvisional(quality({ human_replies: 20, classified: 6 }))).toBe(true);
  });

  it("is settled on a real sample that has been classified", () => {
    expect(qualityIsProvisional(quality())).toBe(false);
  });
});

describe("breakdownRows", () => {
  it("drops empty labels and sorts by count", () => {
    const rows = breakdownRows(quality());
    expect(rows.map((r) => r.label)).toEqual(["interested", "objection", "neutral", "not_now"]);
    expect(rows.every((r) => r.count > 0)).toBe(true);
  });

  it("computes each label's share of classified replies", () => {
    const rows = breakdownRows(quality());
    expect(rows[0].share).toBeCloseTo(6 / 18, 5);
  });

  it("is empty without data", () => {
    expect(breakdownRows(undefined)).toEqual([]);
  });

  it("never divides by zero", () => {
    const rows = breakdownRows(quality({
      breakdown: { interested: 0, neutral: 0, objection: 0, not_now: 0, unsubscribe: 0 },
    }));
    expect(rows).toEqual([]);
  });
});

describe("intentExplanation", () => {
  it("is honest when nothing has been decided", () => {
    expect(intentExplanation(null)).toBe("Not classified yet.");
    expect(intentExplanation({
      label: null, confidence: null, reason: null, source: null, at: null, is_positive: false,
    })).toBe("Not classified yet.");
  });

  it("gives the label, the confidence and the reason", () => {
    expect(intentExplanation({
      label: "interested", confidence: 0.9, reason: "Asked to book Thursday.",
      source: "model", at: "2026-09-16T00:00:00Z", is_positive: true,
    })).toBe("Interested · 90% confident — Asked to book Thursday.");
  });

  it("says when a rule decided it, so nobody reads it as a model opinion", () => {
    expect(intentExplanation({
      label: "unsubscribe", confidence: 1, reason: null, source: "rules",
      at: null, is_positive: false,
    })).toBe("Unsubscribe · 100% confident · decided by rule");
  });
});
