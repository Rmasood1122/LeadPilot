import { describe, expect, it } from "vitest";
import {
  channelLabel,
  dayLabel,
  formatDuration,
  groupByDay,
  itemTitle,
  openSuggestions,
  type ChannelSuggestion,
  type ThreadItem,
} from "@/lib/conversation";

function item(overrides: Partial<ThreadItem>): ThreadItem {
  return { id: Math.random().toString(36), kind: "message", direction: "outbound",
           channel: "email", at: "2026-09-13T10:00:00+00:00", ...overrides };
}

describe("itemTitle", () => {
  it("describes sends by status", () => {
    expect(itemTitle(item({ status: "sent", step_no: 2 }))).toBe("Email sent (step 2)");
    expect(itemTitle(item({ status: "scheduled" }))).toBe("Email scheduled");
    expect(itemTitle(item({ status: "bounced" }))).toBe("Email bounced");
    expect(itemTitle(item({ status: "needs_template", channel: "whatsapp" }))).toBe("WhatsApp not sent");
  });
  it("describes every other kind", () => {
    expect(itemTitle(item({ kind: "reply", channel: "linkedin", direction: "inbound" }))).toBe("LinkedIn reply");
    expect(itemTitle(item({ kind: "call", channel: "phone", outcome: "not_interested" })))
      .toBe("AI call — not interested");
    expect(itemTitle(item({ kind: "booking", channel: "calendar" }))).toBe("Meeting booked");
    expect(itemTitle(item({ kind: "channel_suggestion", channel: "linkedin", from_channel: "email",
                            direction: "system" }))).toBe("Suggested switch: Email → LinkedIn");
  });
});

describe("grouping", () => {
  it("groups consecutive items by day and keeps order", () => {
    const groups = groupByDay([
      item({ at: "2026-09-12T09:00:00+00:00" }), item({ at: "2026-09-12T17:00:00+00:00" }),
      item({ at: "2026-09-13T08:00:00+00:00" }), item({ at: null }),
    ]);
    expect(groups.map((g) => [g.day, g.items.length])).toEqual([
      ["2026-09-12", 2], ["2026-09-13", 1], ["undated", 1]]);
  });
  it("labels days in UTC", () => {
    expect(dayLabel("2026-09-13")).toBe("Sun, 13 Sept 2026".replace("Sept", new Date("2026-09-13T00:00:00Z")
      .toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" })));
    expect(dayLabel("undated")).toBe("Undated");
  });
});

describe("misc", () => {
  it("labels channels", () => {
    expect(channelLabel("whatsapp")).toBe("WhatsApp");
    expect(channelLabel("sms")).toBe("sms");
  });
  it("formats call durations", () => {
    expect(formatDuration(245)).toBe("4m 5s");
    expect(formatDuration(40)).toBe("40s");
    expect(formatDuration(null)).toBe("");
  });
  it("keeps only open suggestions", () => {
    const base: ChannelSuggestion = { id: "1", lead_id: "l", from_channel: "email",
      to_channel: "linkedin", sends_without_reply: 3, reason: "", status: "suggested",
      switched_message_id: null, created_at: null, decided_at: null };
    expect(openSuggestions([base, { ...base, id: "2", status: "dismissed" }])).toHaveLength(1);
  });
});
