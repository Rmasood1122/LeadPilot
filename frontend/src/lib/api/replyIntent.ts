import { api } from "./client";
import type { ReplyIntent, ReplyQuality } from "../replyIntent";

/** Part 1 Feature 1 — the positive reply classifier's API surface. */

export const getReplyIntent = (replyId: string) =>
  api<ReplyIntent>(`/crm/replies/${replyId}/intent`);

export const reclassifyReplyIntent = (replyId: string) =>
  api<ReplyIntent>(`/crm/replies/${replyId}/intent/reclassify`, { method: "POST" });

export const getReplyQuality = (strategyId: string) =>
  api<ReplyQuality & { strategy_id: string }>(`/strategies/${strategyId}/reply-quality`);
