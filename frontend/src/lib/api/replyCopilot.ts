import { api } from "./client";
import type {
  CopilotMetrics,
  CopilotSettings,
  CopilotStatus,
  DraftPage,
  ReplyDraft,
} from "../replyCopilot";

/** F04 Reply Copilot — the draft queue. Every route is 404 while the
 *  `reply_copilot_enabled` system setting is off. */

export function listReplyDrafts(
  opts: { status?: CopilotStatus | "all"; leadId?: string; limit?: number } = {},
) {
  const params = new URLSearchParams();
  params.set("status", opts.status ?? "pending");
  if (opts.leadId) params.set("lead_id", opts.leadId);
  params.set("limit", String(opts.limit ?? 50));
  return api<DraftPage>(`/reply-copilot/drafts?${params.toString()}`);
}

/** NOTE: `body` is passed as an OBJECT. api() stringifies it itself — passing
 *  JSON.stringify here would send a JSON *string* and FastAPI would answer
 *  422. See the fixed-bug note at the bottom of ./client.ts. */
export const approveReplyDraft = (id: string, payload: { subject?: string; body?: string } = {}) =>
  api<ReplyDraft>(`/reply-copilot/drafts/${id}/approve`, { method: "POST", body: payload });

export const copyReplyDraft = (id: string, payload: { body?: string } = {}) =>
  api<ReplyDraft>(`/reply-copilot/drafts/${id}/copy`, { method: "POST", body: payload });

export const discardReplyDraft = (id: string) =>
  api<ReplyDraft>(`/reply-copilot/drafts/${id}/discard`, { method: "POST" });

export const getReplyCopilotSettings = () => api<CopilotSettings>("/reply-copilot/settings");

export const setReplyCopilotAutoSend = (on: boolean) =>
  api<CopilotSettings>("/reply-copilot/settings", {
    method: "PUT", body: { auto_send_meeting_time: on },
  });

/** Per-account: may an answer to a later reply pass the stop an earlier
 *  reply caused? (default true; false = strict). */
export const setReplyCopilotAnswerEarlier = (on: boolean) =>
  api<CopilotSettings>("/reply-copilot/settings", {
    method: "PUT", body: { answer_earlier_replies: on },
  });

export const getReplyCopilotMetrics = (days = 30) =>
  api<CopilotMetrics>(`/reply-copilot/metrics?days=${days}`);
