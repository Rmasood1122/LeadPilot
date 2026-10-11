/**
 * "Find leads" and "Create sequence and launch" contract.
 *
 * The server endpoints already existed but nothing in the app called them, so
 * a verified strategy could not source or contact anyone. These tests pin:
 *  - what goes on the wire (JSON objects, correct paths and verbs),
 *  - the pure rules that decide what the UI offers,
 *  - that launching is blocked until the person has confirmed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { createSequence, enrollSequence, sourceLeads } from "@/lib/api/outreach";
import {
  MAX_UI_LEADS,
  buildSequenceSteps,
  canLaunchSequence,
  canSourceLeads,
  contactableLeads,
  launchErrorMessage,
  parseMaxLeads,
  sourceErrorMessage,
  sourcingProgress,
} from "@/lib/leadOutreach";
import type { LeadOut } from "@/lib/api/types";

let calls: { url: string; init: RequestInit }[] = [];

beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({}), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  }));
});
afterEach(() => { vi.unstubAllGlobals(); });

function last() {
  const c = calls[calls.length - 1];
  return { url: c.url, method: c.init.method, body: JSON.parse(c.init.body as string) };
}

function lead(status: LeadOut["status"], email: string | null = "a@b.co"): LeadOut {
  return {
    id: Math.random().toString(36).slice(2), full_name: "A", title: null,
    company: null, email, phone: null, status, enrichment_json: null,
  };
}

describe("wire format", () => {
  it("sourceLeads posts max_leads to the strategy's source endpoint", async () => {
    await sourceLeads("s1", 5);
    const r = last();
    expect(r.url).toContain("/strategies/s1/leads/source");
    expect(r.method).toBe("POST");
    expect(r.body).toEqual({ max_leads: 5 });
  });

  it("createSequence posts the steps as an object", async () => {
    await createSequence("s1", {
      name: "Outreach", steps: buildSequenceSteps({ openingBrief: "Intro", followUpBrief: "", followUpDays: 3 }),
    });
    const r = last();
    expect(r.url).toContain("/strategies/s1/sequences");
    expect(r.method).toBe("POST");
    expect(r.body.name).toBe("Outreach");
    expect(r.body.channel).toBe("email");
    expect(r.body.steps).toHaveLength(1);
  });

  it("enrollSequence enrolls verified leads only, with the lawful-basis confirmation", async () => {
    await enrollSequence("q1", "launch-lawful-basis-2026-10-11");
    const r = last();
    expect(r.url).toContain("/sequences/q1/enroll");
    expect(r.method).toBe("POST");
    expect(r.body).toEqual({
      lead_statuses: ["verified"],
      lawful_basis_confirmed: true,
      lawful_basis_text_version: "launch-lawful-basis-2026-10-11",
    });
  });
});

describe("source offer", () => {
  it("only a verified strategy can source", () => {
    expect(canSourceLeads("verified")).toBe(true);
    for (const s of ["pending", "researching", "verifying", "needs_human_review",
                     "failed", "executing", "budget_exhausted"] as const) {
      expect(canSourceLeads(s)).toBe(false);
    }
  });

  it("parseMaxLeads accepts 1..cap and rejects the rest", () => {
    expect(parseMaxLeads("5")).toBe(5);
    expect(parseMaxLeads(String(MAX_UI_LEADS))).toBe(MAX_UI_LEADS);
    expect(parseMaxLeads(String(MAX_UI_LEADS + 1))).toBeNull();
    expect(parseMaxLeads("0")).toBeNull();
    expect(parseMaxLeads("2.5")).toBeNull();
    expect(parseMaxLeads("")).toBeNull();
    expect(parseMaxLeads("abc")).toBeNull();
  });
});

describe("sourcing progress", () => {
  it("is running while any lead is mid-chain", () => {
    const p = sourcingProgress([lead("sourced"), lead("verified")]);
    expect(p.running).toBe(true);
    expect(p.total).toBe(2);
  });
  it("is finished once every lead reached an end state", () => {
    const p = sourcingProgress([lead("verified"), lead("flagged"), lead("dropped")]);
    expect(p.running).toBe(false);
    expect(p.counts.verified).toBe(1);
  });
  it("no leads means nothing to show", () => {
    expect(sourcingProgress([]).total).toBe(0);
  });
});

describe("who can be contacted", () => {
  it("only verified leads that have an email", () => {
    const leads = [lead("verified"), lead("verified", null), lead("flagged"), lead("sourced")];
    expect(contactableLeads(leads)).toHaveLength(1);
  });
});

describe("sequence steps", () => {
  it("one email step with no wait when there is no follow-up", () => {
    const s = buildSequenceSteps({ openingBrief: " Intro ", followUpBrief: "  ", followUpDays: 3 });
    expect(s).toHaveLength(1);
    expect(s[0]).toMatchObject({ step_no: 1, template: "Intro", delay_days: 0 });
  });
  it("adds a numbered follow-up with the chosen wait", () => {
    const s = buildSequenceSteps({ openingBrief: "Intro", followUpBrief: "Nudge", followUpDays: 4 });
    expect(s.map((x) => x.step_no)).toEqual([1, 2]);
    expect(s[1]).toMatchObject({ template: "Nudge", delay_days: 4 });
  });
});

describe("launch gate", () => {
  const ok = { status: "verified" as const, contactable: 3, openingBrief: "Intro", confirmed: true };
  it("allows a launch when everything is in place", () => {
    expect(canLaunchSequence(ok)).toBe(true);
  });
  it("is blocked until the person confirms", () => {
    expect(canLaunchSequence({ ...ok, confirmed: false })).toBe(false);
  });
  it("is blocked with no contactable leads, no brief, or an unverified strategy", () => {
    expect(canLaunchSequence({ ...ok, contactable: 0 })).toBe(false);
    expect(canLaunchSequence({ ...ok, openingBrief: "   " })).toBe(false);
    expect(canLaunchSequence({ ...ok, status: "needs_human_review" })).toBe(false);
  });
});

describe("error wording", () => {
  it("passes the server's reason for a 409", () => {
    expect(launchErrorMessage(new ApiError(409, "campaign is paused: bounce rate")))
      .toBe("campaign is paused: bounce rate");
  });
  it("explains a phone-verification refusal", () => {
    expect(launchErrorMessage(new ApiError(403, "PHONE_NOT_VERIFIED"))).toMatch(/phone/i);
  });
  it("is plain for a network failure and for rate limits", () => {
    expect(launchErrorMessage(new Error("x"))).toMatch(/connection/i);
    expect(sourceErrorMessage(new ApiError(429, "slow down"))).toMatch(/wait/i);
  });
  it("tells the person sourcing needs a verified strategy", () => {
    expect(sourceErrorMessage(new ApiError(409, "strategy status is 'verifying'")))
      .toMatch(/verifying/);
  });
});
