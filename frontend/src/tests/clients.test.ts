import { describe, expect, it } from "vitest";

import {
  billingMismatch,
  clientSubtitle,
  money,
  poolWarning,
  rate,
  sortClients,
  statusTone,
  unassignedWarning,
  type ClientBilling,
  type ClientOverview,
  type ClientReport,
  type ClientWorkspace,
} from "@/lib/clients";

function client(overrides: Partial<ClientWorkspace & ClientReport> = {}):
  ClientWorkspace & ClientReport {
  return {
    id: "c1", name: "Blaze Safety", slug: "blaze-safety", status: "active",
    contact_name: null, contact_email: null, billing_email: "ap@blaze.test",
    billing_reference: null, monthly_fee_cents: 200000,
    per_meeting_fee_cents: 15000, currency: "GBP", notes: null,
    sending_domains: ["blaze-outreach.com"], strategy_count: 2,
    archived_at: null, created_at: "2026-09-01T00:00:00Z",
    client_id: "c1", strategies: 2, leads: 120, sent: 340, replies: 41,
    meetings: 6, won: 1, reply_rate: 0.1206, meeting_rate: 0.0176,
    revenue_cents: 450000,
    ...overrides,
  };
}

describe("money", () => {
  it("renders integer cents as the client's currency", () => {
    expect(money(200000, "USD")).toBe("$2,000.00");
  });

  it("renders an unrecognised but well-formed code rather than blanking", () => {
    // Intl accepts any three-letter code, so this is the common case: the
    // number is still readable even when the symbol is not known.
    expect(money(150000, "ZZZ")).toContain("1,500.00");
  });

  it("falls back rather than throwing on a malformed code", () => {
    // Intl throws on anything that is not three letters, and an invoice that
    // throws is worse than one with an ugly currency label.
    expect(money(150000, "Z")).toBe("1500.00 Z");
  });

  it("treats a missing amount as zero rather than NaN", () => {
    expect(money(null, "USD")).toBe("$0.00");
  });
});

describe("rate", () => {
  it("shows an em dash rather than 0% for a rate that does not exist", () => {
    expect(rate(null)).toBe("—");
    expect(rate(0.1206)).toBe("12%");
  });
});

describe("statusTone", () => {
  it("distinguishes running from paused from archived", () => {
    expect(statusTone("active")).toBe("success");
    expect(statusTone("paused")).toBe("warning");
    expect(statusTone("archived")).toBe("default");
  });
});

describe("clientSubtitle", () => {
  it("names the campaigns, the meetings and the reserved domains", () => {
    expect(clientSubtitle(client()))
      .toBe("2 campaigns · 6 meetings · blaze-outreach.com");
  });

  it("says plainly when no domain is reserved", () => {
    expect(clientSubtitle(client({ sending_domains: [] })))
      .toContain("no sending domain reserved");
  });

  it("uses the singular for one of each", () => {
    expect(clientSubtitle(client({ strategy_count: 1, meetings: 1 })))
      .toContain("1 campaign · 1 meeting");
  });
});

describe("poolWarning", () => {
  it("is silent once a domain is reserved", () => {
    expect(poolWarning(client())).toBeNull();
  });

  it("says an empty pool is permissive, rather than letting someone assume isolation", () => {
    const text = poolWarning(client({ sending_domains: [] })) as string;
    expect(text).toContain("can send from any connected mailbox");
  });
});

describe("unassignedWarning", () => {
  function overview(n: number): ClientOverview {
    return { clients: [], unassigned_strategies: n, note: "" };
  }

  it("is silent when everything is filed", () => {
    expect(unassignedWarning(overview(0))).toBeNull();
    expect(unassignedWarning(null)).toBeNull();
  });

  it("says why it matters, not just that it happened", () => {
    expect(unassignedWarning(overview(3)))
      .toBe("3 campaigns are not filed under a client. That work is not on any invoice.");
  });

  it("uses the singular for one", () => {
    expect(unassignedWarning(overview(1))).toContain("1 campaign is not filed");
  });
});

describe("sortClients", () => {
  it("puts active clients first, then the busiest", () => {
    const rows = [
      client({ id: "paused", name: "Paused Co", status: "paused", meetings: 20 }),
      client({ id: "quiet", name: "Quiet Co", meetings: 1 }),
      client({ id: "busy", name: "Busy Co", meetings: 9 }),
    ];
    expect(sortClients(rows).map((c) => c.id)).toEqual(["busy", "quiet", "paused"]);
  });

  it("breaks a tie by name so the list is stable", () => {
    const rows = [client({ id: "b", name: "B Co", meetings: 2 }),
                  client({ id: "a", name: "A Co", meetings: 2 })];
    expect(sortClients(rows).map((c) => c.id)).toEqual(["a", "b"]);
  });

  it("does not mutate its input", () => {
    const rows = [client({ id: "z", name: "Z", meetings: 0 }),
                  client({ id: "a", name: "A", meetings: 9 })];
    sortClients(rows);
    expect(rows[0].id).toBe("z");
  });
});

describe("billingMismatch", () => {
  function billing(overrides: Partial<ClientBilling> = {}): ClientBilling {
    return {
      client_id: "c1", name: "Blaze Safety", currency: "GBP",
      period_start: "2026-09-01", retainer_cents: 200000,
      per_meeting_fee_cents: 15000, meetings_this_period: 2,
      variable_cents: 30000, total_cents: 230000,
      billing_email: null, billing_reference: null,
      lines: [{ label: "Monthly retainer", amount_cents: 200000 },
              { label: "2 meetings booked x 150.00", amount_cents: 30000 }],
      ...overrides,
    };
  }

  it("is silent when the arithmetic agrees", () => {
    expect(billingMismatch(billing())).toBeNull();
    expect(billingMismatch(null)).toBeNull();
  });

  it("names both numbers when it does not", () => {
    const text = billingMismatch(billing({ total_cents: 999999 })) as string;
    expect(text).toContain("£2,300.00");
    expect(text).toContain("£9,999.99");
  });
});
