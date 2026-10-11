import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  attemptText,
  canOverride,
  canRefresh,
  panelVisible,
  sendDecisionText,
  totalCostUnits,
  verdictLabel,
  verdictTone,
  type Attempt,
  type EmailVerdict,
} from "@/lib/bounce-shield";
import { clearEmailOverride, refreshEmailVerdict, setEmailOverride } from "@/lib/api/bounceShield";

function data(overrides: Partial<EmailVerdict> = {}): EmailVerdict {
  return {
    lead_id: "l1",
    email: "sara@blaze.test",
    verdict: {
      verdict: "valid", provider: "apollo", verifier: "hunter", score: 95,
      legacy_status: "deliverable", claimed_status: "verified",
      checked_at: "2026-10-01T10:00:00+00:00",
    },
    verdict_is_stale_address: false,
    override: null,
    send_decision: { shield_enabled: true, allowed: true, would_allow: true, tag: "valid",
                     reason: null },
    attempts: [],
    settings: { enabled: true, waterfall_enabled: true, catch_all_policy: "block",
                max_age_days: 90 },
    ...overrides,
  };
}

const blocked = (reason: string, verdict: EmailVerdict["verdict"] = null) =>
  data({
    verdict,
    send_decision: { shield_enabled: true, allowed: false, would_allow: false, tag: null,
                     reason },
  });

describe("verdict label and tone", () => {
  it("names each verdict", () => {
    expect(verdictLabel(data())).toBe("Verified valid");
    expect(verdictTone(data())).toBe("success");
    const catchAll = data({ verdict: { ...data().verdict!, verdict: "catch_all" } });
    expect(verdictLabel(catchAll)).toBe("Catch-all domain");
    expect(verdictTone(catchAll)).toBe("warning");
    const invalid = data({ verdict: { ...data().verdict!, verdict: "invalid" } });
    expect(verdictTone(invalid)).toBe("destructive");
  });

  it("says when there is nothing to judge", () => {
    expect(verdictLabel(data({ email: null }))).toBe("No email address");
    expect(verdictLabel(data({ verdict: null }))).toBe("Not verified");
    expect(verdictLabel(data({ verdict_is_stale_address: true })))
      .toBe("Address changed since verification");
    expect(verdictTone(data({ verdict_is_stale_address: true }))).toBe("default");
  });
});

describe("send decision text", () => {
  it("explains a hold with the server's reason", () => {
    expect(sendDecisionText(blocked("catch-all domain (policy: block) - override to send")))
      .toBe("Email is held: catch-all domain (policy: block) - override to send.");
  });

  it("distinguishes verified from overridden", () => {
    expect(sendDecisionText(data())).toBe("Email will send: the address is verified.");
    expect(sendDecisionText(data({
      send_decision: { shield_enabled: true, allowed: true, would_allow: true,
                       tag: "override", reason: null },
    }))).toBe("Email will send: a manager allowed this address.");
  });

  it("never claims a block while the shield is off", () => {
    const off = data({
      send_decision: { shield_enabled: false, allowed: true, would_allow: false, tag: null,
                       reason: "no verification on record" },
    });
    expect(sendDecisionText(off)).toMatch(/^Bounce Shield is off\./);
    expect(sendDecisionText(off)).toContain("would be held");
  });
});

describe("which actions are offered", () => {
  it("offers override only for a held, non-undeliverable address", () => {
    expect(canOverride(blocked("unknown"))).toBe(true);
    expect(canOverride(data())).toBe(false);                       // already sending
    expect(canOverride(blocked("undeliverable", {
      ...data().verdict!, verdict: "invalid" }))).toBe(false);
    expect(canOverride({ ...blocked("x"), email: null })).toBe(false);
    expect(canOverride({ ...blocked("x"),
      override: { by: "u", at: "2026-10-01T00:00:00Z", reason: "r", verdict_at_override: null },
    })).toBe(false);
    expect(canOverride({ ...blocked("x"),
      send_decision: { shield_enabled: false, allowed: true, would_allow: false, tag: null,
                       reason: "x" } })).toBe(false);
  });

  it("offers re-verify when either flag is on", () => {
    expect(canRefresh(data())).toBe(true);
    expect(canRefresh(data({ settings: { enabled: false, waterfall_enabled: false,
                                         catch_all_policy: "block", max_age_days: 90 } })))
      .toBe(false);
  });

  it("hides the panel when the feature is off and nothing was recorded", () => {
    const off = data({ verdict: null, settings: { enabled: false, waterfall_enabled: false,
                                                  catch_all_policy: "block", max_age_days: 90 } });
    expect(panelVisible(off)).toBe(false);
    expect(panelVisible(data())).toBe(true);
    expect(panelVisible(undefined)).toBe(false);
  });
});

describe("attempts", () => {
  const a = (o: Partial<Attempt>): Attempt => ({
    id: "a", step: "hunter", provider: "hunter", operation: "verify", outcome: "catch_all",
    cached: false, cost_units: 1, claimed_status: null, email_domain: "blaze.test",
    created_at: null, ...o,
  });

  it("describes cost honestly", () => {
    expect(attemptText(a({}))).toBe("hunter verified: catch all (1 unit)");
    expect(attemptText(a({ cached: true, cost_units: 0, operation: "find_email",
                            outcome: "candidate" })))
      .toBe("hunter searched: candidate (cache hit, no charge)");
    expect(totalCostUnits([a({}), a({ cost_units: 2 }), a({ cached: true })])).toBe(3);
  });
});

describe("write helpers send a JSON object", () => {
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
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("setEmailOverride", async () => {
    await setEmailOverride("l1", "Met at the trade show");
    const last = calls[calls.length - 1];
    expect(last.url).toContain("/leads/l1/email-override");
    expect(last.init.method).toBe("POST");
    expect(JSON.parse(last.init.body as string)).toEqual({ reason: "Met at the trade show" });
  });

  it("refreshEmailVerdict and clearEmailOverride", async () => {
    await refreshEmailVerdict("l1");
    expect(calls[calls.length - 1].init.method).toBe("POST");
    expect(calls[calls.length - 1].url).toContain("/leads/l1/email-verdict/refresh");
    await clearEmailOverride("l1");
    expect(calls[calls.length - 1].init.method).toBe("DELETE");
  });
});
