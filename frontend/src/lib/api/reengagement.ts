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

/* ---------------------------------------------------------------------------
 * Part 1 Feature 7 — re-engagement memory ("not now" is not "never").
 *
 * A different object from the campaign settings above: these are per-PROSPECT
 * dated return visits created by a "not now" reply, each carrying the reason
 * that prospect gave, in their words.
 * ------------------------------------------------------------------------ */

export type ReasonKind =
  | "budget" | "contract" | "timing" | "project" | "headcount" | "priority"
  | "unspecified";
export type PlanStatus = "scheduled" | "due" | "sent" | "cancelled";

export interface ReengagementPlan {
  id: string;
  lead: { id: string; full_name: string | null; company: string | null;
          email: string | null; status: string | null } | null;
  reason_kind: ReasonKind | null;
  reason_label: string;
  reason_text: string | null;
  /** True when the PROSPECT named the date — a different promise from a
   *  90-day guess, and the UI says which. */
  date_from_prospect: boolean;
  stated_return_on: string | null;
  due_at: string | null;
  interval_days: number | null;
  status: PlanStatus;
  message_id: string | null;
  outcome: string | null;
  cancelled_reason: string | null;
  created_at: string | null;
}

export interface ReengagementPlanPage {
  total: number;
  limit: number;
  offset: number;
  status: string | null;
  items: ReengagementPlan[];
}

export const listReengagementPlans = (
  status: PlanStatus | "all" = "scheduled",
): Promise<ReengagementPlanPage> => api(`/reengagement/plans?status=${status}`);

export const getLeadReengagementPlans = (leadId: string): Promise<ReengagementPlan[]> =>
  api(`/leads/${leadId}/reengagement-plans`);

/** `body` is an OBJECT — api() stringifies it itself. */
export const rescheduleReengagementPlan = (id: string, dueOn: string) =>
  api<ReengagementPlan>(`/reengagement/plans/${id}/reschedule`,
                        { method: "POST", body: { due_on: dueOn } });

export const cancelReengagementPlan = (id: string, reason: string) =>
  api<ReengagementPlan>(`/reengagement/plans/${id}/cancel`,
                        { method: "POST", body: { reason } });
