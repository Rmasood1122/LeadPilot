/** Feature A4 — the unified cross-channel conversation, shaped for the lead
 *  page. Pure; tested in src/tests/conversation.test.ts. */

export type ThreadKind = "message" | "reply" | "call" | "booking" | "meeting" | "channel_suggestion";

export interface ThreadItem {
  id: string;
  kind: ThreadKind;
  direction: "outbound" | "inbound" | "both" | "system";
  channel: string;
  at: string | null;
  status?: string | null;
  subject?: string | null;
  body?: string | null;
  step_no?: number | null;
  opened?: boolean | null;
  open_count?: number | null;
  classification?: string | null;
  authenticity?: { kind: string; buyer_intent_score: number | null; confidence: number | null } | null;
  outcome?: string | null;
  duration_seconds?: number | null;
  starts_at?: string | null;
  from_channel?: string | null;
  suggestion_id?: string | null;
}

export interface ChannelSuggestion {
  id: string;
  lead_id: string;
  from_channel: string;
  to_channel: string;
  sends_without_reply: number;
  reason: string;
  status: "suggested" | "accepted" | "auto_switched" | "dismissed";
  switched_message_id: string | null;
  created_at: string | null;
  decided_at: string | null;
}

const CHANNELS: Record<string, string> = {
  email: "Email", linkedin: "LinkedIn", whatsapp: "WhatsApp", phone: "Phone",
  calendar: "Calendar", meeting: "Meeting",
};

export function channelLabel(channel: string): string {
  return CHANNELS[channel] ?? channel;
}

/** A one-line title for an entry: "Email sent", "WhatsApp reply", "Call — interested". */
export function itemTitle(item: ThreadItem): string {
  const ch = channelLabel(item.channel);
  switch (item.kind) {
    case "message":
      if (item.status === "scheduled") return `${ch} scheduled`;
      if (item.status === "bounced") return `${ch} bounced`;
      if (item.status === "failed" || item.status === "needs_template") return `${ch} not sent`;
      return `${ch} sent${item.step_no ? ` (step ${item.step_no})` : ""}`;
    case "reply":
      return `${ch} reply`;
    case "call":
      return `AI call${item.outcome ? ` — ${item.outcome.replace(/_/g, " ")}` : ""}`;
    case "booking":
      return "Meeting booked";
    case "meeting":
      return `Meeting${item.status ? ` (${item.status.replace(/_/g, " ")})` : ""}`;
    case "channel_suggestion":
      return `Suggested switch: ${channelLabel(item.from_channel ?? "")} → ${ch}`;
    default:
      return ch;
  }
}

export interface DayGroup {
  day: string;
  items: ThreadItem[];
}

/** Consecutive items grouped by UTC calendar day, in thread order; undated last. */
export function groupByDay(items: ThreadItem[]): DayGroup[] {
  const groups: DayGroup[] = [];
  for (const item of items) {
    const day = item.at ? item.at.slice(0, 10) : "undated";
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.items.push(item);
    else groups.push({ day, items: [item] });
  }
  return groups;
}

/** "2026-09-13" -> "Sun, 13 Sep 2026". */
export function dayLabel(day: string): string {
  if (day === "undated") return "Undated";
  const date = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return day;
  return date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short",
                                             year: "numeric", timeZone: "UTC" });
}

export function openSuggestions(suggestions: ChannelSuggestion[]): ChannelSuggestion[] {
  return suggestions.filter((s) => s.status === "suggested");
}

/** 245 -> "4m 5s". */
export function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return "";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m ? `${m}m ${s}s` : `${s}s`;
}
