/** Feature Group 3 — revenue analytics, costs, funnel, smart send time and
 *  reply sentiment. Money is integer cents throughout, exactly as the API
 *  returns it; format only at the edge (lib/revenue.ts). */

import { api } from "./client";

export interface CampaignRevenueRow {
  strategy_id: string;
  name: string;
  campaign_state: string;
  sends: number;
  meetings: number;
  deals_won: number;
  revenue_cents: number;
  direct_cost_cents: number;
  api_cost_cents: number;
  voice_cost_cents: number;
  allocated_cost_cents: number;
  total_cost_cents: number;
  cost_per_meeting_cents: number | null;
  cost_per_deal_cents: number | null;
  roi: number | null;
}

export interface RevenueReport {
  currency: string;
  date_from: string;
  date_to: string;
  campaigns: CampaignRevenueRow[];
  totals: {
    revenue_cents: number;
    cost_cents: number;
    meetings: number;
    deals_won: number;
    sends: number;
    cost_per_meeting_cents: number | null;
    cost_per_deal_cents: number | null;
    roi: number | null;
    open_pipeline_cents: number;
    unattributed_revenue_cents: number;
    unallocated_cost_cents: number;
  };
  monthly: { month: string; revenue_cents: number; cost_cents: number }[];
  notes: {
    excluded_deals: number;
    excluded_costs: number;
    usd_costs_excluded: boolean;
    api_cost_usd_cents: number;
    voice_cost_usd_cents: number;
  };
  api_usage: {
    provider: string;
    purpose: string;
    calls: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd_cents: number;
  }[];
}

export type CostCategory = "data" | "tools" | "ai" | "time" | "ads" | "other";

export interface CampaignCost {
  id: string;
  strategy_id: string | null;
  category: CostCategory;
  description: string;
  amount_cents: number;
  amount: number;
  currency: string;
  hours: number | null;
  incurred_on: string;
  created_at: string | null;
}

export interface CostInput {
  strategy_id?: string | null;
  category: CostCategory;
  description?: string;
  amount?: number | null;
  hours?: number | null;
  hourly_rate?: number | null;
  currency?: string;
  incurred_on?: string | null;
}

export interface FunnelStep {
  step_no: number;
  channel: string;
  variant: string;
  sent: number;
  opened: number;
  replied: number;
  booked: number;
  dropped: number;
  in_progress: number;
  open_rate: number | null;
  reply_rate: number | null;
  booking_rate: number | null;
  drop_off_rate: number | null;
}

export interface FunnelReport {
  sequences: { id: string; name: string; channel: string; steps: FunnelStep[] }[];
  best_step: { sequence_id: string; sequence_name: string; step_no: number; reply_rate: number } | null;
  best_step_min_sent?: number;
}

export interface SendWindow {
  dow: number; // Monday = 0
  hour: number;
  score: number;
  share: number;
  opens: number;
  replies: number;
}

export interface HeatCell {
  dow: number;
  hour: number;
  opens: number;
  replies: number;
  score: number;
  schedulable: boolean;
}

export interface SendTimeStatus {
  smart_send_time: boolean;
  windows: SendWindow[];
  computed_at: string | null;
  opens: number;
  min_opens: number;
  max_delay_hours: number;
  heatmap: HeatCell[];
  rescheduled?: number;
  result?: string;
}

export interface SentimentWeek {
  week_start: string;
  total: number;
  interested: number;
  question: number;
  objection: number;
  not_interested: number;
  unsubscribe: number;
  objection_rate: number | null;
  interested_rate: number | null;
  alerted: boolean;
  partial: boolean;
}

export interface SentimentTrend {
  weeks: SentimentWeek[];
  threshold: number;
  min_replies: number;
}

export function getRevenue(dateFrom: string, dateTo: string): Promise<RevenueReport> {
  const q = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
  return api(`/analytics/revenue?${q}`);
}

export function listCosts(strategyId?: string): Promise<{ total: number; items: CampaignCost[] }> {
  const q = new URLSearchParams({ limit: "200" });
  if (strategyId) q.set("strategy_id", strategyId);
  return api(`/costs?${q}`);
}

export function createCost(body: CostInput): Promise<CampaignCost> {
  return api("/costs", { method: "POST", body });
}

export function deleteCost(id: string): Promise<void> {
  return api(`/costs/${id}`, { method: "DELETE" });
}

export function getFunnel(strategyId: string): Promise<FunnelReport> {
  return api(`/strategies/${strategyId}/funnel`);
}

export function getSendTime(strategyId: string): Promise<SendTimeStatus> {
  return api(`/strategies/${strategyId}/send-time`);
}

export function setSmartSendTime(strategyId: string, on: boolean): Promise<SendTimeStatus> {
  return api(`/strategies/${strategyId}/send-time`, {
    method: "PUT",
    body: { smart_send_time: on },
  });
}

export function recomputeSendTime(strategyId: string): Promise<SendTimeStatus> {
  return api(`/strategies/${strategyId}/send-time/recompute`, { method: "POST" });
}

export function getSentiment(strategyId: string, weeks = 12): Promise<SentimentTrend> {
  return api(`/strategies/${strategyId}/sentiment?weeks=${weeks}`);
}
