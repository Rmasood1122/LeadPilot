import { describe, expect, it } from "vitest";

import {
  ageLabel,
  orderSignals,
  safeHref,
  signalHeadline,
  sourceText,
  statusLabel,
  statusTone,
  type LeadSignal,
  type LeadSignals,
} from "@/lib/signals";

function signal(overrides: Partial<LeadSignal> = {}): LeadSignal {
  return {
    id: "s1", type: "funding", type_label: "Funding", source: "newsapi",
    source_label: "Company news", source_name: "TechWire",
    source_url: "https://news.example/a", title: "Acme raises $20M",
    excerpt: null, observed_at: "2026-10-01T00:00:00Z",
    expires_at: "2026-12-30T00:00:00Z", first_seen_at: "2026-10-02T00:00:00Z",
    age_days: 10, confidence: 0.7, freshness: 0.86, score: 0.6, status: "fresh",
    citable: true, not_citable_reason: null, ...overrides,
  };
}

function data(overrides: Partial<LeadSignals> = {}): LeadSignals {
  const signals = overrides.signals ?? [signal()];
  return {
    lead_id: "l1", enabled: true, claim_verification: true, signals,
    top: signals.find((s) => s.citable) ?? null, ...overrides,
  };
}

describe("safeHref", () => {
  it("allows only http and https", () => {
    expect(safeHref("https://news.example/a")).toBe("https://news.example/a");
    expect(safeHref("http://news.example/a")).toBe("http://news.example/a");
    expect(safeHref("javascript:alert(1)")).toBeNull();
    expect(safeHref("data:text/html,hi")).toBeNull();
    expect(safeHref("not a url")).toBeNull();
    expect(safeHref(null)).toBeNull();
  });
});

describe("ageLabel", () => {
  it("names the age in words", () => {
    expect(ageLabel(0)).toBe("today");
    expect(ageLabel(1)).toBe("yesterday");
    expect(ageLabel(12)).toBe("12 days ago");
    expect(ageLabel(45)).toBe("about 2 months ago");
    expect(ageLabel(30)).toBe("30 days ago");
  });
});

describe("status", () => {
  it("maps bands to tones and labels", () => {
    expect(statusTone("fresh")).toBe("success");
    expect(statusTone("aging")).toBe("warning");
    expect(statusTone("expired")).toBe("default");
    expect(statusLabel("expired")).toBe("Expired");
  });
});

describe("sourceText", () => {
  it("adds the publisher when it says something new", () => {
    expect(sourceText(signal())).toBe("Company news · TechWire");
    expect(sourceText(signal({ source_name: null }))).toBe("Company news");
    expect(sourceText(signal({ source_label: "Apollo record", source_name: "Apollo record" })))
      .toBe("Apollo record");
  });
});

describe("signalHeadline", () => {
  it("is empty when the feature is off", () => {
    expect(signalHeadline(data({ enabled: false }))).toBe("");
    expect(signalHeadline(undefined)).toBe("");
  });

  it("says when nothing is on record", () => {
    expect(signalHeadline(data({ signals: [] }))).toMatch(/No dated signals/);
  });

  it("names the top signal and its age, and the claim-check condition", () => {
    const line = signalHeadline(data());
    expect(line).toMatch(/funding/);
    expect(line).toMatch(/10 days ago/);
    expect(line).toMatch(/claim check/);
  });

  it("says why nothing is citable", () => {
    const apolloOnly = signal({ citable: false, source_url: null,
                                not_citable_reason: "no public source link" });
    expect(signalHeadline(data({ signals: [apolloOnly] }))).toMatch(/No citable signal/);
    expect(signalHeadline(data({ signals: [apolloOnly], claim_verification: false })))
      .toMatch(/claim verification is off/);
  });
});

describe("orderSignals", () => {
  it("puts the best score first and breaks ties by recency", () => {
    const a = signal({ id: "a", score: 0.2 });
    const b = signal({ id: "b", score: 0.6, observed_at: "2026-09-01T00:00:00Z" });
    const c = signal({ id: "c", score: 0.6, observed_at: "2026-10-05T00:00:00Z" });
    expect(orderSignals([a, b, c]).map((s) => s.id)).toEqual(["c", "b", "a"]);
  });
});
