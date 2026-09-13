import { describe, expect, it } from "vitest";
import {
  explainSignals,
  intentBand,
  kindLabel,
  kindTone,
  percent,
  type Authenticity,
} from "@/lib/authenticity";

function auth(overrides: Partial<Authenticity>): Authenticity {
  return { kind: "genuine", authenticity_score: 1, buyer_intent_score: 0.5, confidence: 0.8,
           signals: [], scored_at: null, ...overrides };
}

describe("labels and tones", () => {
  it("names every kind", () => {
    expect(kindLabel("out_of_office")).toBe("Out of office");
    expect(kindLabel(null)).toBe("Not scored");
  });
  it("marks machines as noise and people as signal", () => {
    expect(kindTone("genuine")).toBe("success");
    expect(kindTone("out_of_office")).toBe("warning");
    expect(kindTone("bot")).toBe("destructive");
    expect(kindTone(undefined)).toBe("default");
  });
  it("formats percentages", () => {
    expect(percent(0.873)).toBe("87%");
    expect(percent(null)).toBe("—");
  });
});

describe("intentBand", () => {
  it("bands genuine replies by buyer intent", () => {
    expect(intentBand(auth({ buyer_intent_score: 0.9 }))).toBe("hot");
    expect(intentBand(auth({ buyer_intent_score: 0.5 }))).toBe("warm");
    expect(intentBand(auth({ buyer_intent_score: 0.1 }))).toBe("cool");
  });
  it("never gives an automated reply intent", () => {
    expect(intentBand(auth({ kind: "auto_responder", buyer_intent_score: 0.9 }))).toBe("none");
    expect(intentBand(null)).toBe("none");
  });
});

describe("explainSignals", () => {
  it("turns signal codes into de-duplicated reasons", () => {
    expect(explainSignals(["ooo:subject", "ooo:\\bi('m| am)", "classifier:out_of_office",
                           "intent:pricing"]))
      .toEqual(["out-of-office wording", "AI classifier verdict", "asks about price"]);
  });
  it("passes unknown codes through", () => {
    expect(explainSignals(["mystery"])).toEqual(["mystery"]);
  });
});
