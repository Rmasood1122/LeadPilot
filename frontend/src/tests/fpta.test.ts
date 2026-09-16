import { describe, expect, it } from "vitest";

import {
  band,
  bandLabel,
  bandTone,
  dimensionName,
  dimensionQuestion,
  explanationRows,
  isHeuristicOnly,
  scoreText,
  strongestDimension,
  summaryDimensions,
  weakestDimension,
  whyAdvice,
  whyHeadline,
  type FptaDetail,
  type FptaKey,
} from "@/lib/fpta";

const WEIGHTS = { fit: 0.3, problem: 0.3, timing: 0.2, access: 0.2 };

function detail(scores: Partial<Record<FptaKey, number | null>> = {},
                overrides: Partial<FptaDetail> = {}): FptaDetail {
  const merged = { fit: 80, problem: 40, timing: 60, access: 90, ...scores };
  return {
    overall: 66,
    band: "workable",
    fit: merged.fit, problem: merged.problem, timing: merged.timing, access: merged.access,
    scored_at: "2026-09-16T00:00:00Z",
    method: "model",
    weights: WEIGHTS,
    dimensions: (Object.keys(WEIGHTS) as FptaKey[]).map((key) => ({
      key,
      score: merged[key] ?? null,
      reason: `${key} reason`,
      signals: [`${key} signal`],
      baseline: merged[key] ?? null,
      weight: WEIGHTS[key],
    })),
    ...overrides,
  };
}

describe("band", () => {
  it("matches the server's thresholds exactly", () => {
    expect(band(70)).toBe("strong");
    expect(band(69)).toBe("workable");
    expect(band(45)).toBe("workable");
    expect(band(44)).toBe("weak");
    expect(band(0)).toBe("weak");
  });

  it("calls an unscored prospect unscored, not weak", () => {
    expect(band(null)).toBe("unscored");
    expect(band(undefined)).toBe("unscored");
    expect(bandLabel("unscored")).toBe("Not scored");
    expect(bandTone("unscored")).toBe("default");
  });
});

describe("scoreText", () => {
  it("shows an em dash rather than a zero for an unscored dimension", () => {
    expect(scoreText(null)).toBe("—");
    expect(scoreText(0)).toBe("0");
  });
});

describe("dimension naming", () => {
  it("names all four", () => {
    expect((["fit", "problem", "timing", "access"] as FptaKey[]).map(dimensionName))
      .toEqual(["Fit", "Problem", "Timing", "Access"]);
  });

  it("carries the question each dimension answers", () => {
    expect(dimensionQuestion("problem")).toContain("evidence");
    expect(dimensionQuestion("access")).toContain("reach");
  });
});

describe("summaryDimensions", () => {
  it("returns the four in a fixed order so columns line up", () => {
    const row = { fpta_overall: 66, fpta_fit: 80, fpta_problem: 40,
                  fpta_timing: 60, fpta_access: 90 };
    expect(summaryDimensions(row)).toEqual([
      { key: "fit", score: 80 }, { key: "problem", score: 40 },
      { key: "timing", score: 60 }, { key: "access", score: 90 },
    ]);
  });

  it("survives a row from an older API build with no F-P-T-A fields", () => {
    expect(summaryDimensions({})).toEqual([
      { key: "fit", score: null }, { key: "problem", score: null },
      { key: "timing", score: null }, { key: "access", score: null },
    ]);
  });
});

describe("strongest / weakest", () => {
  it("finds the drag on the overall", () => {
    expect(weakestDimension(detail())?.key).toBe("problem");
    expect(strongestDimension(detail())?.key).toBe("access");
  });

  it("breaks a tie by weight, so the more important one is named", () => {
    const tied = detail({ fit: 50, problem: 50, timing: 50, access: 50 });
    expect(weakestDimension(tied)?.weight).toBe(0.3);
  });

  it("is null when nothing has been scored", () => {
    const unscored = detail({ fit: null, problem: null, timing: null, access: null });
    expect(weakestDimension(unscored)).toBeNull();
    expect(strongestDimension(unscored)).toBeNull();
  });
});

describe("whyHeadline", () => {
  it("names the specific signals rather than saying 'good fit'", () => {
    expect(whyHeadline(detail()))
      .toBe("Scores 66/100 — access is the strongest signal, problem is the weakest.");
  });

  it("admits when nothing has been scored", () => {
    expect(whyHeadline(null)).toContain("Not scored yet");
    expect(whyHeadline(detail({}, { overall: null }))).toContain("Not scored yet");
  });

  it("does not name the same dimension twice", () => {
    const one = detail({ fit: 50, problem: null, timing: null, access: null });
    expect(whyHeadline(one)).toBe("Scores 66/100 — fit is the strongest signal.");
  });
});

describe("whyAdvice", () => {
  it("gives the next action for the weakest dimension", () => {
    expect(whyAdvice(detail({ problem: 20 }))).toContain("their own words");
    expect(whyAdvice(detail({ fit: 10, problem: 80, timing: 80, access: 80 })))
      .toContain("ICP");
    expect(whyAdvice(detail({ access: 5, fit: 80, problem: 80, timing: 80 })))
      .toContain("route");
  });

  it("stays quiet when nothing is weak enough to act on", () => {
    expect(whyAdvice(detail({ fit: 80, problem: 75, timing: 70, access: 90 }))).toBeNull();
  });

  it("stays quiet for an unscored prospect", () => {
    expect(whyAdvice(null)).toBeNull();
  });
});

describe("explanationRows", () => {
  it("reads as an argument: strongest first", () => {
    expect(explanationRows(detail()).map((r) => r.key))
      .toEqual(["access", "fit", "timing", "problem"]);
  });

  it("puts unscored dimensions last rather than treating them as zero-ish", () => {
    const rows = explanationRows(detail({ problem: null }));
    expect(rows[rows.length - 1].key).toBe("problem");
  });

  it("is empty without data", () => {
    expect(explanationRows(undefined)).toEqual([]);
  });
});

describe("isHeuristicOnly", () => {
  it("flags only the pure fallback", () => {
    expect(isHeuristicOnly(detail({}, { method: "heuristic" }))).toBe(true);
    expect(isHeuristicOnly(detail({}, { method: "mixed" }))).toBe(false);
    expect(isHeuristicOnly(detail())).toBe(false);
    expect(isHeuristicOnly(null)).toBe(false);
  });
});
