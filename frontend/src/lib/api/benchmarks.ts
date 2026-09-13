/** Feature 6 — anonymised benchmarks. */

import { api } from "./client";

export type BenchmarkMetric = "reply_rate" | "meeting_rate" | "bounce_rate";

export interface BenchmarkBucket {
  industry: string;
  /** A band ("10+", "25+", "100+"), never an exact count. */
  accounts: string;
  window_days: number;
  computed_at: string;
  metrics: Partial<Record<BenchmarkMetric, { p25: number; p50: number; p75: number }>>;
}

export interface BenchmarkChannel {
  channel: string;
  yours: { dispatched: number; enough_data: boolean } & Record<BenchmarkMetric, number | null>;
  /** null = no bucket published (too few accounts) for this industry + channel. */
  industry: BenchmarkBucket | null;
  all_industries: BenchmarkBucket | null;
}

export interface BenchmarkComparison {
  industry: string;
  window_days: number;
  min_accounts: number;
  min_account_sends: number;
  channels: BenchmarkChannel[];
  definitions: Record<BenchmarkMetric, string>;
  note: string;
}

export function getBenchmarks(strategyId?: string): Promise<BenchmarkComparison> {
  return api(`/benchmarks${strategyId ? `?strategy_id=${strategyId}` : ""}`);
}
