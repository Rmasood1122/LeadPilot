import { api } from "./client";
import type { InboxReply } from "../authenticity";

export interface InboxQuery {
  kind?: "genuine" | "out_of_office" | "auto_responder" | "bot" | "bounce" | "automated";
  sort?: "newest" | "intent";
  minIntent?: number;
  limit?: number;
  offset?: number;
}

export function listReplies(q: InboxQuery = {}) {
  const params = new URLSearchParams();
  if (q.kind) params.set("kind", q.kind);
  if (q.sort) params.set("sort", q.sort);
  if (q.minIntent !== undefined) params.set("min_intent", String(q.minIntent));
  params.set("limit", String(q.limit ?? 50));
  params.set("offset", String(q.offset ?? 0));
  return api<{ total: number; limit: number; offset: number; items: InboxReply[] }>(
    `/crm/replies?${params.toString()}`);
}

export const rescoreReply = (replyId: string) =>
  api<InboxReply>(`/crm/replies/${replyId}/authenticity/rescore`, { method: "POST" });
