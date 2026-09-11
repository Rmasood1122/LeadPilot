/** Feature Group 1 — how an ai_booking_likelihood score is presented.
 *  One place, so the kanban card, the CRM grid and the lead page agree. */

import type { LeadScoreFactors } from "./api/types";

export type ScoreTone = "success" | "accent" | "warning" | "default";

/** High / medium / low bands. `null` (never scored) is its own state, never
 *  "low": an unscored lead is unknown, not bad. */
export function scoreBand(score: number | null | undefined): {
  tone: ScoreTone;
  label: string;
} {
  if (score === null || score === undefined) return { tone: "default", label: "Not scored" };
  if (score >= 75) return { tone: "success", label: "High" };
  if (score >= 50) return { tone: "accent", label: "Medium" };
  return { tone: "warning", label: "Low" };
}

export const FACTOR_LABELS: Record<
  Exclude<keyof LeadScoreFactors, "heuristic" | "method" | "playbook_booking_rate">,
  string
> = {
  seniority: "Role seniority",
  industry_match: "Industry fit",
  verification: "Email verification",
  company_signals: "Company signals",
  playbook: "Past campaign results",
};

/** Factor rows as 0-100 percentages, strongest first. */
export function factorRows(factors: LeadScoreFactors | null | undefined) {
  if (!factors) return [];
  return (Object.keys(FACTOR_LABELS) as (keyof typeof FACTOR_LABELS)[])
    .map((key) => ({
      key,
      label: FACTOR_LABELS[key],
      percent: Math.round(Math.max(0, Math.min(1, Number(factors[key]) || 0)) * 100),
    }))
    .sort((a, b) => b.percent - a.percent);
}
