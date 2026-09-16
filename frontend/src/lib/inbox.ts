/** Part 1 Feature 6 — the unified cross-channel inbox, shaped for the UI.
 *  Pure; tested in src/tests/inbox.test.ts. */

import { channelLabel } from "./conversation";

export type InboxFilter = "needs_reply" | "all" | "handled";

export interface InboxChannel {
  channel: string;
  inbound: number;
}

export interface InboxLatest {
  reply_id: string;
  channel: string;
  from_address: string;
  subject: string | null;
  preview: string;
  from_a_person: boolean;
  handled_at: string | null;
  intent: string | null;
  intent_confidence: number | null;
  classification: string | null;
}

export interface InboxThread {
  lead: { id: string; full_name: string | null; title: string | null;
          company: string | null; email: string | null; status: string | null };
  channels: InboxChannel[];
  reply_count: number;
  human_reply_count: number;
  unhandled_count: number;
  needs_reply: boolean;
  last_inbound_at: string | null;
  last_human_inbound_at: string | null;
  last_outbound_at: string | null;
  latest: InboxLatest | null;
}

export interface InboxPage {
  total: number;
  limit: number;
  offset: number;
  filter: InboxFilter;
  needs_reply_total: number;
  items: InboxThread[];
}

/** The name at the top of a thread — never an empty row. */
export function threadName(thread: InboxThread): string {
  return thread.lead.full_name
    ?? thread.lead.email
    ?? thread.latest?.from_address
    ?? "Unknown contact";
}

/** "Owner at Blaze Safety" — the one line of context under the name. */
export function threadSubtitle(thread: InboxThread): string {
  return [thread.lead.title, thread.lead.company].filter(Boolean).join(" at ");
}

/** "Email, LinkedIn" — which channels this person has actually used, busiest
 *  first, so the reply goes back on the one they answer. */
export function channelSummary(thread: InboxThread): string {
  return thread.channels.map((c) => channelLabel(c.channel)).join(", ");
}

/** "2 days ago" / "just now". A thread whose age is invisible never gets
 *  prioritised. */
export function relativeTime(iso: string | null, now: Date = new Date()): string {
  if (!iso) return "";
  const ms = now.getTime() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "";
  if (ms < 0) return "just now";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "1 day ago" : `${days} days ago`;
}

/** True once a waiting reply has gone cold enough that answering it needs an
 *  apology. Two days, not seven: a cold prospect who wrote back is warm for
 *  about as long as it takes them to forget they wrote. */
export function isOverdue(thread: InboxThread, now: Date = new Date()): boolean {
  if (!thread.needs_reply || !thread.last_human_inbound_at) return false;
  return now.getTime() - new Date(thread.last_human_inbound_at).getTime()
    > 2 * 24 * 3_600_000;
}

/** What the row's badge says about the newest message. */
export function latestBadge(thread: InboxThread): { text: string; tone: "success" | "warning" | "destructive" | "default" } | null {
  const latest = thread.latest;
  if (!latest) return null;
  if (!latest.from_a_person) {
    return { text: (latest.classification ?? "automated").replace(/_/g, " "), tone: "default" };
  }
  if (latest.intent === "interested") return { text: "Interested", tone: "success" };
  if (latest.intent === "not_now") return { text: "Not now", tone: "warning" };
  if (latest.intent === "objection") return { text: "Objection", tone: "destructive" };
  if (latest.intent === "unsubscribe") return { text: "Unsubscribe", tone: "destructive" };
  return null;
}

/** The count for the "Needs reply" tab. Threads, not messages: one prospect
 *  who wrote three times is one thing to do. */
export function badgeCount(page: InboxPage | null | undefined): number {
  return page?.needs_reply_total ?? 0;
}

export function emptyLabel(filter: InboxFilter): string {
  if (filter === "needs_reply") return "Nothing is waiting on you. ";
  if (filter === "handled") return "Nothing has been cleared yet.";
  return "No replies on any channel yet.";
}
