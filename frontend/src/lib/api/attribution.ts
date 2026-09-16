import { api } from "./client";
import type { AttributionEntry, AttributionSummary, OutcomeKind } from "../attribution";

/** Part 1 Feature 8 — the transparent attribution ledger. */

export interface AttributionPage {
  total: number;
  limit: number;
  offset: number;
  items: AttributionEntry[];
}

export function listAttribution(
  opts: { outcomeKind?: OutcomeKind; strategyId?: string; limit?: number } = {},
) {
  const params = new URLSearchParams();
  if (opts.outcomeKind) params.set("outcome_kind", opts.outcomeKind);
  if (opts.strategyId) params.set("strategy_id", opts.strategyId);
  params.set("limit", String(opts.limit ?? 100));
  return api<AttributionPage>(`/attribution?${params.toString()}`);
}

export const getAttributionSummary = (strategyId?: string) =>
  api<AttributionSummary>(
    `/attribution/summary${strategyId ? `?strategy_id=${strategyId}` : ""}`);

export const getLeadAttribution = (leadId: string) =>
  api<AttributionEntry[]>(`/leads/${leadId}/attribution`);

/** Idempotent server-side: UNIQUE(outcome_kind, outcome_id) means pressing
 *  this twice can never double-credit. */
export const recomputeAttribution = () =>
  api<{ checked: number; recorded: number; skipped: number; failed: number }>(
    "/attribution/recompute", { method: "POST" });
