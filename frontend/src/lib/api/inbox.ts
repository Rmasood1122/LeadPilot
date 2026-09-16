import { api } from "./client";
import type { InboxFilter, InboxPage, InboxThread } from "../inbox";
import type { ThreadItem } from "../conversation";

/** Part 1 Feature 6 — the unified cross-channel inbox. */

export interface InboxThreadDetail {
  lead_id: string;
  items: ThreadItem[];
  summary: Record<string, unknown>;
  inbox: InboxThread;
}

export function listInbox(
  opts: { filter?: InboxFilter; channel?: string; limit?: number; offset?: number } = {},
) {
  const params = new URLSearchParams();
  params.set("filter", opts.filter ?? "needs_reply");
  if (opts.channel) params.set("channel", opts.channel);
  params.set("limit", String(opts.limit ?? 50));
  params.set("offset", String(opts.offset ?? 0));
  return api<InboxPage>(`/inbox?${params.toString()}`);
}

export const countInbox = () => api<{ needs_reply: number }>("/inbox/count");

export const getInboxThread = (leadId: string) =>
  api<InboxThreadDetail>(`/inbox/${leadId}`);

/** NOTE: `body` is passed as an OBJECT. api() stringifies it itself — passing
 *  JSON.stringify here would send a JSON *string* and FastAPI would answer
 *  422. See the fixed-bug note at the bottom of ./client.ts. */
export const setThreadHandled = (leadId: string, handled = true) =>
  api<InboxThread & { lead_id: string; changed: number }>(
    `/inbox/${leadId}/handled`, { method: "POST", body: { handled } });

export const setReplyHandled = (replyId: string, handled = true) =>
  api<{ reply_id: string; changed: number; handled_at: string | null }>(
    `/inbox/replies/${replyId}/handled`, { method: "POST", body: { handled } });
