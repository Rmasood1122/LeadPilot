import { describe, expect, it } from "vitest";
import { factorRows, scoreBand } from "@/lib/lead-score";
import { splitSections, zonesByPhase } from "@/lib/strategy-sections";

describe("scoreBand", () => {
  it("bands scores and keeps unscored distinct from low", () => {
    expect(scoreBand(90).label).toBe("High");
    expect(scoreBand(75).label).toBe("High");
    expect(scoreBand(74).label).toBe("Medium");
    expect(scoreBand(10).label).toBe("Low");
    expect(scoreBand(null).label).toBe("Not scored");
    expect(scoreBand(undefined).tone).toBe("default");
    expect(scoreBand(0).label).toBe("Low");
  });
});

describe("factorRows", () => {
  it("returns percentages strongest first and clamps", () => {
    const rows = factorRows({
      seniority: 1, industry_match: 0.15, verification: 0.5,
      company_signals: 2, playbook: -1, playbook_booking_rate: null,
      heuristic: 55, method: "model",
    });
    expect(rows[0]).toMatchObject({ percent: 100 });
    expect(rows.map((r) => r.percent)).toEqual([100, 100, 50, 15, 0]);
    expect(factorRows(null)).toEqual([]);
  });
});

describe("splitSections", () => {
  const doc = [
    "# Client Acquisition Strategy",
    "",
    "## Phase 1: Offering synthesis",
    "Body one",
    "```",
    "## not a heading inside a fence",
    "```",
    "## Phase 2: ICP synthesis",
    "Body two",
  ].join("\n");

  it("splits on ## headings and reads the phase number", () => {
    const { preamble, sections } = splitSections(doc);
    expect(preamble).toBe("# Client Acquisition Strategy");
    expect(sections.map((s) => [s.phase, s.heading])).toEqual([
      [1, "Phase 1: Offering synthesis"],
      [2, "Phase 2: ICP synthesis"],
    ]);
    expect(sections[0].body).toContain("## not a heading inside a fence");
  });

  it("a mutation section has no phase", () => {
    const { sections } = splitSections("## Strategy mutation — version 2\nx\n## Phase 3: Market\ny");
    expect(sections[0].phase).toBeNull();
    expect(sections[1].phase).toBe(3);
  });

  it("handles empty input", () => {
    expect(splitSections(null)).toEqual({ preamble: "", sections: [] });
  });
});

describe("zonesByPhase", () => {
  it("groups by phase", () => {
    const grouped = zonesByPhase([{ phase: 1, id: "a" }, { phase: 3, id: "b" }, { phase: 1, id: "c" }]);
    expect(grouped.get(1)?.map((z) => z.id)).toEqual(["a", "c"]);
    expect(grouped.get(2)).toBeUndefined();
  });
});
