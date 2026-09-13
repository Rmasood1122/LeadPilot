import { api } from "./client";
import type { SequenceReview } from "../sequenceReview";

export const getSequenceReview = (sequenceId: string) =>
  api<SequenceReview>(`/sequences/${sequenceId}/review`);

export const runSequenceReview = (sequenceId: string) =>
  api<SequenceReview>(`/sequences/${sequenceId}/review`, { method: "POST" });

export const overrideSequenceReview = (sequenceId: string, reason: string) =>
  api<SequenceReview>(`/sequences/${sequenceId}/review/override`, { body: { reason } });
