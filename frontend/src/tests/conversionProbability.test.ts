import { describe, expect, it } from "vitest";
import {
  describeFactor,
  killSignalText,
  probabilityPercent,
  stateTone,
} from "@/lib/conversionProbability";

describe("formatting", () => {
  it("formats probabilities, keeping tiny ones honest", () => {
    expect(probabilityPercent(0.4213)).toBe("42%");
    expect(probabilityPercent(0.004)).toBe("<1%");
    expect(probabilityPercent(0)).toBe("0%");
    expect(probabilityPercent(null)).toBe("—");
  });
  it("tones states", () => {
    expect(stateTone("won")).toBe("success");
    expect(stateTone("cooling")).toBe("warning");
    expect(stateTone("archived")).toBe("destructive");
    expect(stateTone("active")).toBe("primary");
  });
  it("explains kill signals", () => {
    expect(killSignalText("unsubscribed")).toBe("they asked to stop");
    expect(killSignalText("some_new_signal")).toBe("some new signal");
    expect(killSignalText(null)).toBe("");
  });
});

describe("describeFactor", () => {
  it("describes the estimate's evidence", () => {
    expect(describeFactor({ factor: "ai_booking_likelihood", value: 0.3 })).toBe("Starting point: AI score 30%");
    expect(describeFactor({ factor: "unanswered_email", count: 3, multiplier: 0.614 }))
      .toBe("3 unanswered email touches (×0.61)");
    expect(describeFactor({ factor: "unanswered_linkedin", count: 1, multiplier: 0.8 }))
      .toBe("1 unanswered linkedin touch (×0.80)");
    expect(describeFactor({ factor: "reply_interested", multiplier: 6 })).toBe("Replied: interested (×6.00)");
    expect(describeFactor({ factor: "inactivity", idle_days: 12.4, multiplier: 0.9 }))
      .toBe("Quiet for 12 days (×0.90)");
    expect(describeFactor({ factor: "bounced", effect: "kill" })).toBe("the email bounced");
  });
  it("hides factors it has nothing useful to say about", () => {
    expect(describeFactor({ factor: "mystery" })).toBeNull();
  });
});
