/** Deals — revenue linked to a lead and a campaign (strategy). */

import { api } from "./client";

export type DealStage = "open" | "won" | "lost";

export interface Deal {
  id: string;
  name: string;
  /** Decimal value, derived server-side from value_cents. */
  value: number;
  value_cents: number;
  currency: string;
  stage: DealStage;
  close_date: string | null;
  lead_id: string | null;
  strategy_id: string | null;
  source: "manual" | "meeting_outcome" | "hubspot" | "salesforce" | string;
  external_ref: string | null;
  notes: string | null;
  created_at: string;
}

export interface DealInput {
  name?: string | null;
  value: number;
  currency?: string;
  stage?: DealStage;
  close_date?: string | null;
  lead_id?: string | null;
  strategy_id?: string | null;
  notes?: string | null;
}

export function listDeals(params: {
  strategyId?: string;
  stage?: DealStage;
  leadId?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ total: number; items: Deal[] }> {
  const q = new URLSearchParams();
  if (params.strategyId) q.set("strategy_id", params.strategyId);
  if (params.stage) q.set("stage", params.stage);
  if (params.leadId) q.set("lead_id", params.leadId);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.offset) q.set("offset", String(params.offset));
  const qs = q.toString();
  return api(`/deals${qs ? `?${qs}` : ""}`);
}

export function createDeal(body: DealInput): Promise<Deal> {
  return api("/deals", { method: "POST", body });
}

export function updateDeal(id: string, body: Partial<DealInput>): Promise<Deal> {
  return api(`/deals/${id}`, { method: "PATCH", body });
}

export function deleteDeal(id: string): Promise<void> {
  return api(`/deals/${id}`, { method: "DELETE" });
}
