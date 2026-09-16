import { api } from "./client";
import type { SendReviewItem } from "../sendReview";

/** Part 1 Feature 5 — the human review queue for high-risk sends. */

export interface SendReviewQueue {
  total: number;
  limit: number;
  offset: number;
  status: string;
  items: SendReviewItem[];
}

export const listSendReviews = (status: "pending" | "approved" | "rejected" | "all" = "pending") =>
  api<SendReviewQueue>(`/send-reviews?status=${status}`);

export const countSendReviews = () =>
  api<{ pending: number }>("/send-reviews/count");

export const getSendReview = (id: string) =>
  api<SendReviewItem>(`/send-reviews/${id}`);

export const approveSendReview = (
  id: string, payload: { note?: string; subject?: string; body?: string } = {},
) => api<SendReviewItem>(`/send-reviews/${id}/approve`, {
  method: "POST", body: JSON.stringify(payload),
});

export const rejectSendReview = (id: string, note: string) =>
  api<SendReviewItem>(`/send-reviews/${id}/reject`, {
    method: "POST", body: JSON.stringify({ note }),
  });
