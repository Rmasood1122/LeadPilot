/** Feature 5 — opt-in post-sequence re-engagement settings. */

import { api } from "./client";

export interface ReengagementStatus {
  enabled: boolean;
  /** false = the admin turned the feature off for the whole deployment. */
  allowed: boolean;
  delay_days: number;
  daily_cap: number;
  weekly_cap: number;
  /** What actually applies after the admin ceilings clamp the campaign's values. */
  effective: { daily_cap: number; weekly_cap: number; delay_days: number };
  ceilings: { daily_cap: number; weekly_cap: number; min_delay_days: number };
  sent_today: number;
  sent_this_week: number;
  /** Leads that would qualify right now, counted as if it were on. */
  eligible_now: number;
  eligible_scan_limit: number;
  channels: string[];
}

export type ReengagementPatch = Partial<
  Pick<ReengagementStatus, "enabled" | "delay_days" | "daily_cap" | "weekly_cap">
>;

export function getReengagement(strategyId: string): Promise<ReengagementStatus> {
  return api(`/strategies/${strategyId}/reengagement`);
}

/** Owners and managers only; values outside the ceilings are a 422. */
export function updateReengagement(
  strategyId: string,
  body: ReengagementPatch,
): Promise<ReengagementStatus> {
  return api(`/strategies/${strategyId}/reengagement`, { method: "PUT", body });
}
