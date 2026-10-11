import { api } from "./client";

/** Mirrors app/api/analytics.py PipelineHealthOut. */
export interface PipelineHealth {
  score: number;
  band: "critical" | "low" | "moderate" | "strong" | string;
  message: string;
  components: { reply_rate: number; completion: number; freshness: number; conversations: number };
  updated_at: string | null;
}

/** GET /strategies/{id}/health -- recomputed live, every plan. */
export function getPipelineHealth(strategyId: string): Promise<PipelineHealth> {
  return api(`/strategies/${strategyId}/health`);
}
