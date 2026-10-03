import { describe, expect, it } from "vitest";

import {
  bulkOwnerChoices,
  canDistribute,
  ownerChoices,
  ownerLabel,
  type TeamContext,
} from "../lib/crm/assignment";

const members = [
  { user_id: "owner-1", email: "owner@team.dev", role: "owner" as const, joined_at: null },
  { user_id: "mgr-1", email: "mgr@team.dev", role: "manager" as const, joined_at: null },
  { user_id: "sdr-1", email: "sdr@team.dev", role: "sdr" as const, joined_at: null },
  { user_id: "sdr-2", email: "sdr2@team.dev", role: "sdr" as const, joined_at: null },
];

const as = (meId: string, role: TeamContext["role"]): TeamContext => ({ members, meId, role });

describe("ownerLabel", () => {
  it("names the signed-in person as You, others by email", () => {
    expect(ownerLabel("sdr-1", as("sdr-1", "sdr"))).toBe("You");
    expect(ownerLabel("sdr-2", as("sdr-1", "sdr"))).toBe("sdr2@team.dev");
    expect(ownerLabel(null, as("sdr-1", "sdr"))).toBe("—");
  });

  it("does not pretend a removed member's lead is unassigned", () => {
    expect(ownerLabel("gone-9", as("mgr-1", "manager"))).toBe("Former member");
  });
});

describe("ownerChoices mirrors the server rule", () => {
  it("managers and owners may pick any member or unassign", () => {
    for (const [me, role] of [["mgr-1", "manager"], ["owner-1", "owner"]] as const) {
      const values = ownerChoices(as(me, role), "sdr-2").map((c) => c.value);
      expect(values).toEqual([null, "owner-1", "mgr-1", "sdr-1", "sdr-2"]);
    }
  });

  it("an SDR may claim an unassigned lead or release their own, nothing else", () => {
    const sdr = as("sdr-1", "sdr");
    expect(ownerChoices(sdr, null).map((c) => c.value)).toEqual([null, "sdr-1"]);
    expect(ownerChoices(sdr, "sdr-1").map((c) => c.value)).toEqual(["sdr-1", null]);
    // A colleague's lead is read-only.
    expect(ownerChoices(sdr, "sdr-2")).toEqual([]);
  });

  it("viewers and an unknown role get a read-only cell", () => {
    expect(ownerChoices(as("x", "viewer"), null)).toEqual([]);
    expect(ownerChoices({ members, meId: "x", role: undefined }, null)).toEqual([]);
  });
});

describe("bulk and round-robin", () => {
  it("offers an SDR only claim and release in bulk", () => {
    expect(bulkOwnerChoices(as("sdr-1", "sdr")).map((c) => c.value)).toEqual(["sdr-1", null]);
    expect(bulkOwnerChoices(as("v", "viewer"))).toEqual([]);
  });

  it("round-robin is a manager action", () => {
    expect(canDistribute("owner")).toBe(true);
    expect(canDistribute("manager")).toBe(true);
    expect(canDistribute("sdr")).toBe(false);
    expect(canDistribute(undefined)).toBe(false);
  });
});
