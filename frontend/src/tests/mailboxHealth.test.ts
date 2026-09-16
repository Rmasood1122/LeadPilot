import { describe, expect, it } from "vitest";

import type { MailboxHealth } from "@/lib/api/trust";
import {
  authGaps,
  bandTone,
  fleetWarning,
  rateText,
  scoreText,
  sortForDisplay,
  stateLabel,
  stateTone,
  throttleExplanation,
} from "@/lib/mailboxHealth";

function mailbox(overrides: Partial<MailboxHealth> = {}): MailboxHealth {
  return {
    mailbox_ref: "mb-1", channel: "email", address: "sara@blaze.test",
    domain: "blaze.test", score: 90, band: "good", state: "healthy",
    throttle_cap: null, daily_cap: 40, reason: null, reasons: [],
    auth: { spf: true, dkim: true, dmarc: true, dmarc_policy: "reject" },
    complaint_rate: 0.0002, complaint_source: "proxy", bounce_rate: 0.004,
    sends_today: 12, sends_7d: 70, paused_at: null, resumed_at: null,
    checked_at: "2026-09-16T12:00:00Z",
    ...overrides,
  };
}

describe("labels and tones", () => {
  it("says what is happening in words, not a slug", () => {
    expect(stateLabel("healthy")).toBe("Sending normally");
    expect(stateLabel("throttled")).toBe("Throttled");
    expect(stateLabel("paused")).toBe("Paused");
  });

  it("tones a paused mailbox as the emergency it is", () => {
    expect(stateTone("paused")).toBe("destructive");
    expect(stateTone("throttled")).toBe("warning");
    expect(stateTone("healthy")).toBe("success");
  });

  it("gives an unchecked mailbox a neutral tone, not a bad one", () => {
    expect(bandTone("unchecked")).toBe("default");
    expect(bandTone("bad")).toBe("destructive");
  });
});

describe("numbers", () => {
  it("shows an em dash rather than a zero for what was never measured", () => {
    expect(scoreText(null)).toBe("—");
    expect(rateText(null)).toBe("—");
    expect(scoreText(0)).toBe("0");
  });

  it("keeps two decimals, because 0.05% and 0.5% are different problems", () => {
    expect(rateText(0.0032)).toBe("0.32%");
    expect(rateText(0.0005)).toBe("0.05%");
  });
});

describe("throttleExplanation", () => {
  it("is silent for a healthy mailbox", () => {
    expect(throttleExplanation(mailbox())).toBeNull();
  });

  it("promises a paused mailbox's queue is held, not cancelled", () => {
    const text = throttleExplanation(mailbox({ state: "paused" })) as string;
    expect(text).toContain("held, not cancelled");
  });

  it("names both the reduced and the normal limit", () => {
    expect(throttleExplanation(mailbox({ state: "throttled", throttle_cap: 10 })))
      .toContain("10 instead of 40");
  });

  it("still explains a throttle when the caps are unknown", () => {
    const text = throttleExplanation(
      mailbox({ state: "throttled", throttle_cap: null, daily_cap: null })) as string;
    expect(text).toBe("Sending is slowed while health recovers.");
  });
});

describe("authGaps", () => {
  it("is empty for a correctly configured domain", () => {
    expect(authGaps(mailbox())).toEqual([]);
  });

  it("names each missing record so the list is a fix list", () => {
    expect(authGaps(mailbox({
      auth: { spf: false, dkim: false, dmarc: false, dmarc_policy: null },
    }))).toEqual(["SPF", "DKIM", "DMARC"]);
  });

  it("flags a monitoring-only DMARC separately from a missing one", () => {
    expect(authGaps(mailbox({
      auth: { spf: true, dkim: true, dmarc: true, dmarc_policy: "none" },
    }))).toEqual(["DMARC is p=none"]);
  });

  it("says nothing about a consumer mailbox whose DNS is not the user's", () => {
    expect(authGaps(mailbox({
      auth: { spf: null, dkim: null, dmarc: null, dmarc_policy: null },
    }))).toEqual([]);
  });
});

describe("sortForDisplay", () => {
  it("puts what needs attention first", () => {
    const rows = [
      mailbox({ mailbox_ref: "ok", state: "healthy", score: 95 }),
      mailbox({ mailbox_ref: "dead", state: "paused", score: 20 }),
      mailbox({ mailbox_ref: "slow", state: "throttled", score: 55 }),
    ];
    expect(sortForDisplay(rows).map((r) => r.mailbox_ref)).toEqual(["dead", "slow", "ok"]);
  });

  it("sorts unchecked mailboxes last rather than treating null as a bad score", () => {
    const rows = [
      mailbox({ mailbox_ref: "unknown", state: "healthy", score: null }),
      mailbox({ mailbox_ref: "known", state: "healthy", score: 80 }),
    ];
    expect(sortForDisplay(rows).map((r) => r.mailbox_ref)).toEqual(["known", "unknown"]);
  });

  it("does not mutate its input", () => {
    const rows = [mailbox({ mailbox_ref: "a", state: "healthy" }),
                  mailbox({ mailbox_ref: "b", state: "paused" })];
    sortForDisplay(rows);
    expect(rows[0].mailbox_ref).toBe("a");
  });
});

describe("fleetWarning", () => {
  it("is silent when everything is sending", () => {
    expect(fleetWarning([mailbox()])).toBeNull();
    expect(fleetWarning([])).toBeNull();
  });

  it("says outreach is slower than planned, not just that a score dropped", () => {
    const text = fleetWarning([
      mailbox({ state: "paused" }), mailbox({ state: "throttled" }),
    ]) as string;
    expect(text).toBe("1 mailbox paused, 1 throttled — outreach is going out "
      + "slower than planned.");
  });

  it("pluralises correctly", () => {
    expect(fleetWarning([mailbox({ state: "paused" }), mailbox({ state: "paused" })]))
      .toContain("2 mailboxes paused");
  });
});
