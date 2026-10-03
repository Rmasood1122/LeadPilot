import { describe, expect, it } from "vitest";

import {
  TRUST_FLOOR,
  ageLabel,
  confidenceTone,
  flagged,
  hoverText,
  needsChecking,
  provenanceHeadline,
  stalenessTone,
  type LeadProvenance,
  type ProvenanceItem,
} from "@/lib/provenance";

function item(overrides: Partial<ProvenanceItem> = {}): ProvenanceItem {
  return {
    field: "title", label: "Title", source: "apollo", source_label: "Apollo",
    source_note: "From the Apollo data provider — good coverage, not verified.",
    confidence: 0.75, observed_at: "2026-09-01T00:00:00Z",
    staleness: { days: 15, band: "fresh" }, detail: null, value: "Owner",
    ...overrides,
  };
}

function data(overrides: Partial<LeadProvenance> = {}): LeadProvenance {
  const items = overrides.items ?? [item()];
  return {
    lead_id: "l1", tracked: true, updated_at: "2026-09-01T00:00:00Z",
    items, weakest: items[0] ?? null, stale_count: 0,
    ...overrides,
  };
}

describe("tones", () => {
  it("separates a good source from a guess", () => {
    expect(confidenceTone(0.95)).toBe("success");
    expect(confidenceTone(0.6)).toBe("warning");
    expect(confidenceTone(0.35)).toBe("destructive");
  });

  it("gives an unrated field a neutral tone rather than a bad one", () => {
    expect(confidenceTone(null)).toBe("default");
  });

  it("tones age on its own scale", () => {
    expect(stalenessTone("fresh")).toBe("success");
    expect(stalenessTone("stale")).toBe("warning");
    expect(stalenessTone("very_stale")).toBe("destructive");
    expect(stalenessTone("unknown")).toBe("default");
  });
});

describe("ageLabel", () => {
  it("reads naturally at each scale", () => {
    expect(ageLabel(item({ staleness: { days: 0, band: "fresh" } })))
      .toBe("recorded today");
    expect(ageLabel(item({ staleness: { days: 1, band: "fresh" } }))).toBe("1 day old");
    expect(ageLabel(item({ staleness: { days: 20, band: "fresh" } })))
      .toBe("20 days old");
    expect(ageLabel(item({ staleness: { days: 120, band: "stale" } })))
      .toBe("4 months old");
    expect(ageLabel(item({ staleness: { days: 800, band: "very_stale" } })))
      .toBe("2 years old");
  });

  it("says age unknown rather than implying it is new", () => {
    expect(ageLabel(item({ staleness: { days: null, band: "unknown" } })))
      .toBe("age unknown");
  });
});

describe("hoverText", () => {
  it("carries source, confidence, age and the reason in one string", () => {
    expect(hoverText(item()))
      .toBe("Apollo · 75% · 15 days old — From the Apollo data provider — "
        + "good coverage, not verified.");
  });

  it("says unrated rather than 0%", () => {
    expect(hoverText(item({ confidence: null }))).toContain("unrated");
  });
});

describe("needsChecking", () => {
  it("flags a weak source", () => {
    expect(needsChecking(item({ confidence: TRUST_FLOOR - 0.01 }))).toBe(true);
    expect(needsChecking(item({ confidence: TRUST_FLOOR }))).toBe(false);
  });

  it("flags a fact old enough to have changed, however good the source", () => {
    expect(needsChecking(item({
      confidence: 0.95, staleness: { days: 900, band: "very_stale" },
    }))).toBe(true);
  });

  it("does not flag merely stale data from a good source", () => {
    expect(needsChecking(item({ staleness: { days: 100, band: "stale" } }))).toBe(false);
  });
});

describe("provenanceHeadline", () => {
  it("says 'not recorded' rather than implying it came from nowhere", () => {
    expect(provenanceHeadline(data({ tracked: false })))
      .toContain("No provenance recorded");
  });

  it("counts what is tagged, weak and stale", () => {
    expect(provenanceHeadline(data({
      items: [item(), item({ field: "company_size", confidence: 0.35 })],
      stale_count: 1,
    }))).toBe("2 fields tagged · 1 worth checking · 1 over three months old.");
  });

  it("stays simple when everything is solid", () => {
    expect(provenanceHeadline(data())).toBe("1 field tagged.");
  });

  it("is empty without data", () => {
    expect(provenanceHeadline(null)).toBe("");
  });
});

describe("flagged", () => {
  it("returns only the fields worth checking", () => {
    const rows = flagged(data({
      items: [item(), item({ field: "company_size", confidence: 0.3 })],
    }));
    expect(rows.map((r) => r.field)).toEqual(["company_size"]);
  });

  it("is empty without data", () => {
    expect(flagged(undefined)).toEqual([]);
  });
});
