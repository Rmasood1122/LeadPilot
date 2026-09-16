import { api } from "./client";
import type { CompletionMetrics, StrategyCompletion } from "../sequenceCompletion";

/** Part 1 Feature 3 — the sequence completion guarantee and its metric. */

export interface DroppedEnrollment {
  enrollment_id: string;
  lead_id: string;
  status: string | null;
  planned_steps: number | null;
  steps_sent: number;
  outcome: "running" | "completed" | "dropped" | "unknown";
  stop_reason: string | null;
  stop_category: string | null;
  stop_label: string | null;
  authorised: boolean | null;
  completed_at: string | null;
  stopped_at: string | null;
  lead: { id: string; full_name: string | null; company: string | null; email: string | null };
}

export const getStrategyCompletion = (strategyId: string) =>
  api<StrategyCompletion>(`/strategies/${strategyId}/completion`);

export const getSequenceCompletion = (sequenceId: string) =>
  api<CompletionMetrics & { sequence_id: string }>(`/sequences/${sequenceId}/completion`);

export const getDroppedProspects = (strategyId: string, unauthorisedOnly = false) =>
  api<{ strategy_id: string; unauthorised_only: boolean; total: number;
        items: DroppedEnrollment[] }>(
    `/strategies/${strategyId}/completion/dropped?unauthorised_only=${unauthorisedOnly}`);
