/**
 * Incident list for the /status page (src/lib/statusIncidents.ts). The list is
 * hand-edited in a pull request, so the validator is the only thing standing
 * between a typo and a published, wrong incident: every entry in INCIDENTS
 * must pass it, and `npm run build` type-checks the shape.
 */
import { describe, expect, it } from "vitest";

import {
  INCIDENTS,
  isResolved,
  sortIncidents,
  validateIncident,
  type Incident,
} from "@/lib/statusIncidents";

const NOW = new Date("2026-10-11T12:00:00Z");

const GOOD: Incident = {
  id: "2026-10-11-scheduled-sends-delayed",
  title: "Scheduled sends delayed",
  impact: "major",
  components: ["background-processing"],
  updates: [
    { status: "investigating", at: "2026-10-11T09:05:00Z", text: "Scheduled emails are not going out." },
    { status: "resolved", at: "2026-10-11T09:40:00Z", text: "Sends resumed at 09:35 UTC." },
  ],
};

describe("INCIDENTS (the published list)", () => {
  it("every entry passes validation", () => {
    for (const incident of INCIDENTS) {
      expect(validateIncident(incident, NOW), incident.id).toEqual([]);
    }
  });

  it("ids are unique", () => {
    const ids = INCIDENTS.map((i) => i.id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe("validateIncident", () => {
  it("accepts a well-formed incident", () => {
    expect(validateIncident(GOOD, NOW)).toEqual([]);
    expect(isResolved(GOOD)).toBe(true);
  });

  it("rejects an id that does not start with the first update's UTC date", () => {
    expect(validateIncident({ ...GOOD, id: "2026-10-12-scheduled-sends-delayed" }, NOW).join(" ")).toMatch(/date/);
    expect(validateIncident({ ...GOOD, id: "Scheduled Sends" }, NOW).join(" ")).toMatch(/id/);
  });

  it("rejects empty or over-long titles, unknown components, and no updates", () => {
    expect(validateIncident({ ...GOOD, title: "" }, NOW).length).toBeGreaterThan(0);
    expect(validateIncident({ ...GOOD, title: "x".repeat(121) }, NOW).length).toBeGreaterThan(0);
    expect(validateIncident({ ...GOOD, components: ["database-primary"] }, NOW).join(" ")).toMatch(/component/);
    expect(validateIncident({ ...GOOD, components: [] }, NOW).join(" ")).toMatch(/component/);
    expect(validateIncident({ ...GOOD, updates: [] }, NOW).join(" ")).toMatch(/update/);
  });

  it("rejects non-UTC, future, or out-of-order update times", () => {
    const at = (a: string, b: string): Incident => ({
      ...GOOD,
      updates: [
        { ...GOOD.updates[0], at: a },
        { ...GOOD.updates[1], at: b },
      ],
    });
    expect(validateIncident(at("2026-10-11T09:05:00+02:00", "2026-10-11T09:40:00Z"), NOW).join(" ")).toMatch(/UTC/);
    expect(validateIncident(at("2026-10-11T09:05:00Z", "2026-10-11T13:00:00Z"), NOW).join(" ")).toMatch(/future/);
    expect(validateIncident(at("2026-10-11T09:40:00Z", "2026-10-11T09:05:00Z"), NOW).join(" ")).toMatch(/order/);
  });

  it("allows at most one resolved update, and only as the latest", () => {
    const early: Incident = {
      ...GOOD,
      updates: [
        { status: "resolved", at: "2026-10-11T09:05:00Z", text: "Fixed." },
        { status: "monitoring", at: "2026-10-11T09:40:00Z", text: "Watching." },
      ],
    };
    expect(validateIncident(early, NOW).join(" ")).toMatch(/resolved/);
  });

  it("rejects empty update text", () => {
    const blank: Incident = { ...GOOD, updates: [{ ...GOOD.updates[0], text: "  " }, GOOD.updates[1]] };
    expect(validateIncident(blank, NOW).join(" ")).toMatch(/text/);
  });
});

describe("sortIncidents", () => {
  it("open incidents first, then newest first by latest update", () => {
    const older: Incident = { ...GOOD, id: "2026-10-01-older", updates: [
      { status: "investigating", at: "2026-10-01T08:00:00Z", text: "a" },
      { status: "resolved", at: "2026-10-01T09:00:00Z", text: "b" },
    ] };
    const open: Incident = { ...GOOD, id: "2026-09-30-open", updates: [
      { status: "investigating", at: "2026-09-30T08:00:00Z", text: "a" },
    ] };
    expect(sortIncidents([older, GOOD, open]).map((i) => i.id)).toEqual([open.id, GOOD.id, older.id]);
  });
});
