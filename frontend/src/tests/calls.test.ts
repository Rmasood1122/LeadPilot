import { describe, expect, it } from "vitest";
import { OUTCOME_LABEL, formatDuration, outcomeTone } from "@/lib/api/calls";

describe("calls helpers", () => {
  it("formats durations", () => {
    expect(formatDuration(185)).toBe("3:05");
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(-1)).toBe("—");
  });

  it("labels and tones every outcome", () => {
    for (const outcome of Object.keys(OUTCOME_LABEL) as (keyof typeof OUTCOME_LABEL)[]) {
      expect(OUTCOME_LABEL[outcome]).toBeTruthy();
      expect(outcomeTone(outcome)).toBeTruthy();
    }
    expect(outcomeTone("interested")).toBe("success");
    expect(outcomeTone(null)).toBe("default");
  });
});
