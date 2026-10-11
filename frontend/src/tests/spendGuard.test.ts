import { describe, expect, it } from "vitest";
import {
  DISABLED_STATUS,
  accuracySummary,
  accuracyVerdict,
  alertBanner,
  barWidth,
  capTone,
  creditsLabel,
  errorLabel,
  formatUsd,
  isDisabledError,
  parseCapInput,
  percentUsed,
  thresholdReached,
} from "@/lib/spendGuard";

describe("cap progress", () => {
  it("is null without a cap and a percentage with one", () => {
    expect(percentUsed(5, null)).toBeNull();
    expect(percentUsed(5, 0)).toBeNull();
    expect(percentUsed(3, 10)).toBe(30);
    expect(percentUsed(12.5, 10)).toBe(125);
  });
  it("reports the highest threshold reached", () => {
    expect(thresholdReached(null)).toBeNull();
    expect(thresholdReached(49.9)).toBeNull();
    expect(thresholdReached(50)).toBe(50);
    expect(thresholdReached(79.9)).toBe(50);
    expect(thresholdReached(80)).toBe(80);
    expect(thresholdReached(100)).toBe(100);
    expect(thresholdReached(140)).toBe(100);
  });
  it("tones and clamps the bar", () => {
    expect(capTone(10)).toBe("default");
    expect(capTone(55)).toBe("warning");
    expect(capTone(85)).toBe("warning");
    expect(capTone(100)).toBe("danger");
    expect(barWidth(null)).toBe(0);
    expect(barWidth(140)).toBe(100);
    expect(barWidth(-3)).toBe(0);
  });
  it("only shows a banner from 50%, and says what 100% does", () => {
    expect(alertBanner(null)).toBeNull();
    expect(alertBanner(80)).toBe("80% of your monthly spend cap is used.");
    expect(alertBanner(100)).toMatch(/refused/);
    expect(alertBanner(100)).toMatch(/Scheduled sends continue/);
  });
});

describe("cap input", () => {
  it("empty means no cap", () => {
    expect(parseCapInput("  ")).toEqual({ ok: true, value: null });
  });
  it("accepts dollars with a sign and separators, rounded to cents", () => {
    expect(parseCapInput("$1,250.456")).toEqual({ ok: true, value: 1250.46 });
    expect(parseCapInput("25")).toEqual({ ok: true, value: 25 });
  });
  it("refuses junk and out-of-range values (same bounds as the API)", () => {
    expect(parseCapInput("abc").ok).toBe(false);
    expect(parseCapInput("0.5").ok).toBe(false);
    expect(parseCapInput("2000000").ok).toBe(false);
    expect(parseCapInput("1").ok).toBe(true);
  });
});

describe("forecast accuracy", () => {
  it("labels the error ratio", () => {
    expect(errorLabel(null)).toBe("—");
    expect(errorLabel(0)).toBe("exact");
    expect(errorLabel(0.125)).toBe("+12.5% over");
    expect(errorLabel(-0.08)).toBe("-8.0% under");
  });
  it("judges one forecast", () => {
    expect(accuracyVerdict({ reconcilable: false }).text).toMatch(/Refused/);
    expect(accuracyVerdict({ reconcilable: true, complete: false }).text).toMatch(/not measured/);
    expect(accuracyVerdict({ reconcilable: true, complete: true, error_pct: null }).text)
      .toBe("No recorded spend");
    expect(accuracyVerdict({ reconcilable: true, complete: true, error_pct: 0.1,
                             within_tolerance: true }))
      .toEqual({ text: "Within ±25% (+10.0% over)", tone: "default" });
    expect(accuracyVerdict({ reconcilable: true, complete: true, error_pct: -0.4,
                             within_tolerance: false }).tone).toBe("warning");
  });
  it("summarises the metric", () => {
    expect(accuracySummary({ measured_runs: 0, within_tolerance: 0 }))
      .toBe("No finished runs measured yet.");
    expect(accuracySummary({ measured_runs: 4, within_tolerance: 3 }))
      .toBe("3 of 4 finished runs forecast within ±25%.");
  });
});

describe("formatting and errors", () => {
  it("formats dollars and credits", () => {
    expect(formatUsd(null)).toBe("—");
    expect(formatUsd(2.5)).toBe("$2.50");
    expect(creditsLabel({})).toBe("none");
    expect(creditsLabel({ apollo: 1200, hunter: 0, other: 3 })).toBe("1,200 Apollo · 3 Other");
  });
  it("recognises the flag-off 409", () => {
    expect(isDisabledError({ status: DISABLED_STATUS })).toBe(true);
    expect(isDisabledError({ status: 500 })).toBe(false);
    expect(isDisabledError(null)).toBe(false);
  });
});
