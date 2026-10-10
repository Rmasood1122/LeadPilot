/** F07 — Spend Guard. Money is US dollars as the API returns it (floats with
 *  up to 4 decimals); format at the edge (lib/spendGuard.ts formatUsd). */

import { api } from "./client";

export interface ForecastLines {
  kind: "strategy_run" | "enrichment_run" | "quickstart";
  ai: { purposes: string[]; input_tokens: number; output_tokens: number; usd: number };
  data: { credits: Record<string, number>; usd: number };
  sends: { count: number; usd: number; note: string };
  requested_leads: number | null;
  total_usd: number;
  basis: Record<string, unknown>;
}

export interface ForecastPreview {
  would_allow: boolean;
  forecast: ForecastLines;
  cap_usd: number | null;
  spent_this_month_usd: number;
  remaining_usd: number | null;
}

export interface CreditLine {
  forecast: number;
  actual: number;
  error_pct: number | null;
  within_tolerance: boolean | null;
}

export interface Reconciliation {
  forecast_id: string;
  kind: ForecastLines["kind"];
  decision: "allowed" | "refused";
  created_at: string;
  strategy_id: string | null;
  batch_id: string | null;
  forecast_usd: number;
  tolerance: number;
  reconcilable: boolean;
  complete?: boolean;
  actual_usd?: number;
  error_pct?: number | null;
  within_tolerance?: boolean | null;
  ai?: { forecast_usd: number; actual_usd: number; error_pct: number | null };
  data?: { forecast_usd: number; actual_usd: number; credits: Record<string, CreditLine> };
}

export interface SpendAlertRow {
  threshold: 50 | 80 | 100;
  fired_at: string | null;
  spent_usd: number;
  cap_usd: number;
  email_status: "sent" | "failed" | "skipped" | "merged" | "pending";
}

export interface SpendUsage {
  enabled: boolean;
  period: { label: string; start: string; end: string };
  cap: { monthly_cap_usd: number | null; email_alerts: boolean; thresholds: number[] };
  spend: {
    ai_usd: number;
    data_usd: number;
    total_usd: number;
    data_credits: Record<string, number>;
    percent_of_cap: number | null;
    remaining_usd: number | null;
  };
  daily: { plan: string; limit_usd: number | null; spent_today_usd: number };
  pricing: { providers: { provider: string; usd_per_credit: number; priced: boolean }[] };
  billable: {
    verified_results: number;
    finalized_batches: number;
    data_attempts: number;
    paid_data_attempts: number;
    data_credits: Record<string, number>;
    internal_data_usd: number;
    cost_per_verified_result_usd: number | null;
    note: string;
  };
  alerts: SpendAlertRow[];
  forecasts: Reconciliation[];
  accuracy: { measured_runs: number; within_tolerance: number; share_within_tolerance: number | null };
}

export function getSpendUsage(): Promise<SpendUsage> {
  return api("/spend-guard/usage");
}

export function setSpendCap(monthlyCapUsd: number | null, emailAlerts: boolean): Promise<SpendUsage> {
  return api("/spend-guard/cap", {
    method: "PUT",
    body: { monthly_cap_usd: monthlyCapUsd, email_alerts: emailAlerts },
  });
}

export function previewEnrichmentForecast(strategyId: string, maxLeads: number): Promise<ForecastPreview> {
  return api("/spend-guard/forecast", {
    body: { kind: "enrichment_run", strategy_id: strategyId, max_leads: maxLeads },
  });
}
