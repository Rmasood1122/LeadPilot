/**
 * Kanban transition rule tests (Chunk 7) — mirrors the backend
 * _ALLOWED_TRANSITIONS map; the frontend uses canTransition() to decide
 * whether to offer a column as a drop target, and snaps back on 422.
 */

import { describe, it, expect } from "vitest";
import { canTransition, ALLOWED_TRANSITIONS } from "@/lib/api/leads";
import type { LeadStatus } from "@/lib/api/types";

describe("canTransition", () => {
  // Allowed moves
  it("verified → flagged is allowed", () =>
    expect(canTransition("verified", "flagged")).toBe(true));
  it("verified → dropped is allowed", () =>
    expect(canTransition("verified", "dropped")).toBe(true));
  it("flagged → verified is allowed (unflag)", () =>
    expect(canTransition("flagged", "verified")).toBe(true));
  it("contacted → replied is allowed", () =>
    expect(canTransition("contacted", "replied")).toBe(true));
  it("replied → meeting_booked is allowed", () =>
    expect(canTransition("replied", "meeting_booked")).toBe(true));

  // Identity (same column) is always allowed
  const ALL_STATUSES: LeadStatus[] = [
    "sourced", "enriched", "email_found", "verified", "flagged",
    "dropped", "contacted", "replied", "meeting_booked",
  ];
  ALL_STATUSES.forEach(s => {
    it(`${s} → ${s} is identity (always allowed)`, () =>
      expect(canTransition(s, s)).toBe(true));
  });

  // Disallowed moves
  it("sourced → verified is not allowed (pipeline only)", () =>
    expect(canTransition("sourced", "verified")).toBe(false));
  it("dropped → any is not allowed (terminal)", () => {
    ALL_STATUSES.filter(s => s !== "dropped").forEach(to =>
      expect(canTransition("dropped", to)).toBe(false),
    );
  });
  it("meeting_booked → any is not allowed (terminal)", () => {
    ALL_STATUSES.filter(s => s !== "meeting_booked").forEach(to =>
      expect(canTransition("meeting_booked", to)).toBe(false),
    );
  });
  it("verified → meeting_booked is not allowed (skip steps)", () =>
    expect(canTransition("verified", "meeting_booked")).toBe(false));
  it("verified → replied is not allowed", () =>
    expect(canTransition("verified", "replied")).toBe(false));
});

describe("ALLOWED_TRANSITIONS completeness", () => {
  const ALL_STATUSES: LeadStatus[] = [
    "sourced", "enriched", "email_found", "verified", "flagged",
    "dropped", "contacted", "replied", "meeting_booked",
  ];

  it("every lead status has an entry in the transition map", () => {
    for (const s of ALL_STATUSES) {
      expect(ALLOWED_TRANSITIONS).toHaveProperty(s);
    }
  });
});
