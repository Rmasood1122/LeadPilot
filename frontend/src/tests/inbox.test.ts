import { describe, expect, it } from "vitest";

import {
  badgeCount,
  channelSummary,
  emptyLabel,
  isOverdue,
  latestBadge,
  relativeTime,
  threadName,
  threadSubtitle,
  type InboxThread,
} from "@/lib/inbox";

const NOW = new Date("2026-09-16T12:00:00Z");

function thread(overrides: Partial<InboxThread> = {}): InboxThread {
  return {
    lead: { id: "l1", full_name: "Sara Khan", title: "Owner",
            company: "Blaze Safety", email: "sara@blaze.test", status: "replied" },
    channels: [{ channel: "email", inbound: 2 }, { channel: "linkedin", inbound: 1 }],
    reply_count: 3, human_reply_count: 3, unhandled_count: 1, needs_reply: true,
    last_inbound_at: "2026-09-16T10:00:00Z",
    last_human_inbound_at: "2026-09-16T10:00:00Z",
    last_outbound_at: "2026-09-15T09:00:00Z",
    latest: {
      reply_id: "r1", channel: "email", from_address: "sara@blaze.test",
      subject: "Re: inspections", preview: "Sounds interesting — can we talk?",
      from_a_person: true, handled_at: null, intent: "interested",
      intent_confidence: 0.9, classification: null,
    },
    ...overrides,
  };
}

describe("threadName", () => {
  it("prefers the name", () => {
    expect(threadName(thread())).toBe("Sara Khan");
  });

  it("falls back through email, then the sending address", () => {
    expect(threadName(thread({
      lead: { ...thread().lead, full_name: null },
    }))).toBe("sara@blaze.test");
    expect(threadName(thread({
      lead: { ...thread().lead, full_name: null, email: null },
    }))).toBe("sara@blaze.test");
  });

  it("never renders an empty row", () => {
    expect(threadName(thread({
      lead: { ...thread().lead, full_name: null, email: null }, latest: null,
    }))).toBe("Unknown contact");
  });
});

describe("threadSubtitle", () => {
  it("reads as a sentence", () => {
    expect(threadSubtitle(thread())).toBe("Owner at Blaze Safety");
  });

  it("degrades without the title or the company", () => {
    expect(threadSubtitle(thread({ lead: { ...thread().lead, title: null } })))
      .toBe("Blaze Safety");
    expect(threadSubtitle(thread({
      lead: { ...thread().lead, title: null, company: null },
    }))).toBe("");
  });
});

describe("channelSummary", () => {
  it("names the channels in the order the API gave them (busiest first)", () => {
    expect(channelSummary(thread())).toBe("Email, LinkedIn");
  });

  it("is empty when nothing is inbound", () => {
    expect(channelSummary(thread({ channels: [] }))).toBe("");
  });
});

describe("relativeTime", () => {
  it("counts minutes, hours then days", () => {
    expect(relativeTime("2026-09-16T11:30:00Z", NOW)).toBe("30m ago");
    expect(relativeTime("2026-09-16T08:00:00Z", NOW)).toBe("4h ago");
    expect(relativeTime("2026-09-13T12:00:00Z", NOW)).toBe("3 days ago");
    expect(relativeTime("2026-09-15T12:00:00Z", NOW)).toBe("1 day ago");
  });

  it("says 'just now' rather than 0m, and never a negative", () => {
    expect(relativeTime("2026-09-16T11:59:50Z", NOW)).toBe("just now");
    expect(relativeTime("2026-09-17T12:00:00Z", NOW)).toBe("just now");
  });

  it("is empty without a timestamp", () => {
    expect(relativeTime(null, NOW)).toBe("");
  });
});

describe("isOverdue", () => {
  it("flags a reply waiting more than two days", () => {
    expect(isOverdue(thread({ last_human_inbound_at: "2026-09-13T10:00:00Z" }), NOW))
      .toBe(true);
    expect(isOverdue(thread({ last_human_inbound_at: "2026-09-15T10:00:00Z" }), NOW))
      .toBe(false);
  });

  it("never flags a thread nobody is waiting on", () => {
    expect(isOverdue(thread({ needs_reply: false,
                              last_human_inbound_at: "2026-01-01T00:00:00Z" }), NOW))
      .toBe(false);
  });
});

describe("latestBadge", () => {
  it("shows the reply's intent", () => {
    expect(latestBadge(thread())).toEqual({ text: "Interested", tone: "success" });
    expect(latestBadge(thread({ latest: { ...thread().latest!, intent: "objection" } })))
      .toEqual({ text: "Objection", tone: "destructive" });
    expect(latestBadge(thread({ latest: { ...thread().latest!, intent: "not_now" } })))
      .toEqual({ text: "Not now", tone: "warning" });
  });

  it("labels machine mail as what it is, neutrally", () => {
    expect(latestBadge(thread({
      latest: { ...thread().latest!, from_a_person: false, classification: "out_of_office" },
    }))).toEqual({ text: "out of office", tone: "default" });
  });

  it("is silent for an unclassified human reply rather than guessing", () => {
    expect(latestBadge(thread({ latest: { ...thread().latest!, intent: null } })))
      .toBeNull();
  });

  it("is null with nothing inbound", () => {
    expect(latestBadge(thread({ latest: null }))).toBeNull();
  });
});

describe("badgeCount", () => {
  it("reports the server's thread count, not the page length", () => {
    expect(badgeCount({ total: 2, limit: 50, offset: 0, filter: "needs_reply",
                        needs_reply_total: 9, items: [] })).toBe(9);
    expect(badgeCount(null)).toBe(0);
  });
});

describe("emptyLabel", () => {
  it("says something different for each filter", () => {
    const labels = (["needs_reply", "all", "handled"] as const).map(emptyLabel);
    expect(new Set(labels).size).toBe(3);
    expect(emptyLabel("needs_reply")).toContain("Nothing is waiting on you");
  });
});
