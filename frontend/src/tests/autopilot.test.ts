/** Autopilot launch, best time to send, send diagnostics
 *  (docs/features/autopilot-launch.md): the pure logic behind the cards and
 *  what goes on the wire. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  approvedTemplates, bestTimeSavedMessage, blockingCount, canEnable, diagnosticsHeadline,
  intakeCanLaunch, optInBody, overrideError, stateLabel, stateTone, timezoneNote,
  timezoneSources, unreachableNote, type Diagnostics, type LawfulBasis,
} from "@/lib/autopilot";
import { setAutopilot, setAutopilotTemplate, setBestTime } from "@/lib/api/autopilot";
import { createStrategy } from "@/lib/api/strategies";

const BASIS: LawfulBasis = {
  version: "autopilot-lawful-basis-2026-10-11", text: "I confirm ...", label: "When ...",
  available: true,
};

describe("opt-in", () => {
  it("never turns Autopilot on without the confirmation", () => {
    expect(canEnable(false, BASIS)).toBe(false);
    expect(canEnable(true, null)).toBe(false);
    expect(canEnable(true, { ...BASIS, available: false })).toBe(false);
    expect(optInBody(true, false, BASIS)).toEqual({
      enabled: false, lawful_basis_confirmed: false, lawful_basis_text_version: null,
    });
  });

  it("sends the confirmed text version", () => {
    expect(optInBody(true, true, BASIS)).toEqual({
      enabled: true, lawful_basis_confirmed: true,
      lawful_basis_text_version: "autopilot-lawful-basis-2026-10-11",
    });
  });

  it("the wizard can launch with Autopilot off, or on and confirmed", () => {
    expect(intakeCanLaunch(false, false)).toBe(true);
    expect(intakeCanLaunch(true, false)).toBe(false);
    expect(intakeCanLaunch(true, true)).toBe(true);
  });

  it("labels states in plain words", () => {
    expect(stateLabel("waiting_for_review")).toBe("Waiting for your review");
    expect(stateLabel("something_new")).toBe("something new");
    expect(stateTone("launched")).toBe("success");
    expect(stateTone("blocked")).toBe("destructive");
    expect(stateLabel("paused")).toBe("Paused");
    expect(stateTone("paused")).toBe("warning");
  });
});

describe("review fixes", () => {
  it("says how many found leads cannot be contacted, and why", () => {
    expect(unreachableNote(undefined)).toBeNull();
    expect(unreachableNote({})).toBeNull();
    expect(unreachableNote({ a: "suppressed", b: "excluded", c: "suppressed" }))
      .toBe("3 lead(s) Autopilot found cannot be contacted (suppressed: 2, excluded: 1).");
  });

  it("offers only approved WhatsApp templates, never picks one itself", () => {
    const list = [{ id: "a", status: "draft" }, { id: "b", status: "approved" },
                  { id: "c", status: "rejected" }, { id: "d", status: "approved" }];
    expect(approvedTemplates(list).map((t) => t.id)).toEqual(["b", "d"]);
  });

  it("the best-time toast reflects the background reslot (202)", () => {
    expect(bestTimeSavedMessage({ override: { days: [1] }, rescheduling: 4 }))
      .toBe("Saved. 4 scheduled message(s) are being moved into your window.");
    expect(bestTimeSavedMessage({ override: { days: [1] }, rescheduling: 0 }))
      .toMatch(/New messages will go out inside your window/);
    expect(bestTimeSavedMessage({ override: null, rescheduling: 0 }))
      .toBe("Back to the automatic best time.");
  });

  it("names where each lead's local time comes from, in resolution order", () => {
    expect(timezoneSources({ leads: 0, with_timezone: 0, sources: {} })).toBeNull();
    expect(timezoneSources({
      leads: 10, with_timezone: 7,
      sources: { strategy_region: 3, lead_location: 6, lead_recorded: 1 },
    })).toBe("1 from the lead's own time zone, 6 from the lead's country and state, " +
             "3 from the strategy's target region");
  });
});

describe("override window", () => {
  it("matches the server's rules", () => {
    expect(overrideError([], "09:00", "10:00")).toMatch(/at least one day/);
    expect(overrideError([1], "9:00", "10:00")).toMatch(/HH:MM/);
    expect(overrideError([1], "09:10", "10:00")).toMatch(/quarter hours/);
    expect(overrideError([1], "09:00", "09:15")).toMatch(/30 minutes/);
    expect(overrideError([1, 2], "09:00", "10:30")).toBeNull();
  });
});

describe("timezone note", () => {
  it("names the fallback zone, or says nothing when every lead has its own", () => {
    expect(timezoneNote({ leads: 3, with_timezone: 3, fallback: null })).toBeNull();
    expect(timezoneNote({ leads: 10, with_timezone: 7,
                          fallback: { zone: "America/Chicago", source: "strategy_region" } }))
      .toBe("3 of 10 lead(s) have no known location; their local time is taken from " +
            "the strategy's target region (America/Chicago).");
  });
});

describe("diagnostics", () => {
  const reason = (code: string, blocking: boolean) => ({
    code, title: code, detail: null, fix: null, link: null, count: null, blocking,
  });
  const d = (sending: boolean): Diagnostics => ({
    sending, verified_leads_not_enrolled: 0,
    general: [reason("campaign_paused", true)],
    channels: [{ channel: "email", label: "Email", sending: false, scheduled: 1,
                 next_send_at: null,
                 reasons: [reason("send_approval_missing", true), reason("suppressed", false)] }],
  });

  it("counts only blocking reasons", () => {
    expect(blockingCount(d(false))).toBe(2);
    expect(diagnosticsHeadline(d(false))).toBe("2 things are stopping sends.");
    expect(diagnosticsHeadline(d(true))).toMatch(/Nothing is stopping/);
  });
});

describe("wire format", () => {
  let calls: { url: string; init: RequestInit }[] = [];
  beforeEach(() => {
    calls = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({ id: "s1" }), {
        status: 200, headers: { "Content-Type": "application/json" },
      });
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); });
  const body = () => JSON.parse(calls[calls.length - 1].init.body as string);

  it("PUT autopilot sends an object", async () => {
    await setAutopilot("s1", optInBody(true, true, BASIS));
    expect(calls[0].url).toMatch(/\/strategies\/s1\/autopilot$/);
    expect(calls[0].init.method).toBe("PUT");
    expect(body()).toEqual({ enabled: true, lawful_basis_confirmed: true,
                             lawful_basis_text_version: BASIS.version });
  });

  it("best-time override and clear", async () => {
    await setBestTime("s1", { days: [1, 2], start: "09:00", end: "10:00" });
    expect(body()).toEqual({ days: [1, 2], start: "09:00", end: "10:00" });
    await setBestTime("s1", null);
    expect(body()).toEqual({ clear: true });
    expect(calls[1].url).toMatch(/\/strategies\/s1\/best-time$/);
  });

  it("chooses (or clears) the WhatsApp template for Autopilot", async () => {
    await setAutopilotTemplate("s1", "t1");
    expect(calls[0].url).toMatch(/\/strategies\/s1\/autopilot\/whatsapp-template$/);
    expect(calls[0].init.method).toBe("PUT");
    expect(body()).toEqual({ whatsapp_template_id: "t1" });
    await setAutopilotTemplate("s1", null);
    expect(body()).toEqual({ whatsapp_template_id: null });
  });

  it("createStrategy includes autopilot only when it is on", async () => {
    await createStrategy("p1", false, optInBody(false, false, BASIS));
    expect(body()).toEqual({ flow_type: "no_clients" });
    await createStrategy("p1", true, optInBody(true, true, BASIS));
    expect(body().autopilot.enabled).toBe(true);
  });
});
