/** Part 1 Features 2 + 12 — Fit / Problem / Timing / Access, shaped for the
 *  UI, and the "why this prospect" explanation built from it.
 *  Pure; tested in src/tests/fpta.test.ts. */

export type FptaKey = "fit" | "problem" | "timing" | "access";

export const FPTA_KEYS: FptaKey[] = ["fit", "problem", "timing", "access"];

export interface FptaDimension {
  key: FptaKey;
  score: number | null;
  reason: string | null;
  signals: string[];
  baseline: number | null;
  weight: number;
}

export interface FptaDetail {
  lead_id?: string;
  overall: number | null;
  band: FptaBand;
  fit: number | null;
  problem: number | null;
  timing: number | null;
  access: number | null;
  scored_at: string | null;
  method: "model" | "heuristic" | "mixed" | null;
  weights: Record<FptaKey, number>;
  dimensions: FptaDimension[];
  engagement?: string | null;
}

/** The compact shape carried on every lead list row.
 *
 *  Every field is optional: the CRM grid row, the kanban card and the lead
 *  detail all feed this component, and a row from an older API build (or the
 *  published SDK) simply has no F-P-T-A fields — which must render as "not
 *  scored", not as a type error or a zero. */
export interface FptaSummary {
  fpta_overall?: number | null;
  fpta_fit?: number | null;
  fpta_problem?: number | null;
  fpta_timing?: number | null;
  fpta_access?: number | null;
  fpta_scored_at?: string | null;
}

export type FptaBand = "strong" | "workable" | "weak" | "unscored";

const NAMES: Record<FptaKey, string> = {
  fit: "Fit", problem: "Problem", timing: "Timing", access: "Access",
};

/** What each dimension actually asks — shown as the tooltip, because "Fit: 82"
 *  means nothing to someone reading it for the first time. */
const QUESTIONS: Record<FptaKey, string> = {
  fit: "Are they the company and person this offer is for?",
  problem: "Is there evidence they have the problem it solves?",
  timing: "Is something happening now that makes this the moment?",
  access: "Can we reach this person on a channel they answer?",
};

export const dimensionName = (key: FptaKey): string => NAMES[key] ?? key;
export const dimensionQuestion = (key: FptaKey): string => QUESTIONS[key] ?? "";

/** Mirrors app/services/fpta_scoring.band — kept in step deliberately so the
 *  list (which only has the raw numbers) bands identically to the detail. */
export function band(score: number | null | undefined): FptaBand {
  if (score === null || score === undefined) return "unscored";
  if (score >= 70) return "strong";
  if (score >= 45) return "workable";
  return "weak";
}

export function bandTone(value: FptaBand): "success" | "warning" | "destructive" | "default" {
  if (value === "strong") return "success";
  if (value === "workable") return "warning";
  if (value === "weak") return "destructive";
  return "default";
}

export function bandLabel(value: FptaBand): string {
  return { strong: "Strong", workable: "Workable", weak: "Weak", unscored: "Not scored" }[value];
}

/** "82" or "—". Never "0" for an unscored prospect. */
export function scoreText(score: number | null | undefined): string {
  return score === null || score === undefined ? "—" : String(score);
}

/** The four sub-scores from a list row, in a fixed order so columns line up. */
export function summaryDimensions(lead: FptaSummary): { key: FptaKey; score: number | null }[] {
  return [
    { key: "fit", score: lead.fpta_fit ?? null },
    { key: "problem", score: lead.fpta_problem ?? null },
    { key: "timing", score: lead.fpta_timing ?? null },
    { key: "access", score: lead.fpta_access ?? null },
  ];
}

/** The dimension dragging the overall down hardest: lowest score first, and
 *  among equals the one that carries the most weight. Null when unscored. */
export function weakestDimension(detail: FptaDetail | null | undefined): FptaDimension | null {
  const scored = (detail?.dimensions ?? []).filter((d) => d.score !== null);
  if (!scored.length) return null;
  return [...scored].sort((a, b) =>
    (a.score as number) - (b.score as number) || b.weight - a.weight)[0];
}

export function strongestDimension(detail: FptaDetail | null | undefined): FptaDimension | null {
  const scored = (detail?.dimensions ?? []).filter((d) => d.score !== null);
  if (!scored.length) return null;
  return [...scored].sort((a, b) =>
    (b.score as number) - (a.score as number) || b.weight - a.weight)[0];
}

/** Feature 12 — the headline of the "Why this prospect" panel.
 *
 *  Always names the specific signal that drove the score, never a generic
 *  "good fit". An unscored prospect says so rather than being described. */
export function whyHeadline(detail: FptaDetail | null | undefined): string {
  if (!detail || detail.overall === null) {
    return "Not scored yet — no F-P-T-A signals have been read for this prospect.";
  }
  const best = strongestDimension(detail);
  const worst = weakestDimension(detail);
  const lead = best ? `${dimensionName(best.key).toLowerCase()} is the strongest signal` : "";
  const drag = worst && worst.key !== best?.key
    ? `, ${dimensionName(worst.key).toLowerCase()} is the weakest`
    : "";
  return `Scores ${detail.overall}/100 — ${lead}${drag}.`;
}

/** Feature 12 — what to DO about this prospect, from the weakest dimension.
 *  Advice, not a score: a person reading the panel wants the next action. */
export function whyAdvice(detail: FptaDetail | null | undefined): string | null {
  const worst = weakestDimension(detail);
  if (!worst || (worst.score ?? 100) >= 60) return null;
  return {
    fit: "Weak fit. Check this prospect against the ICP before spending a touch on them.",
    problem: "No evidence of the problem yet. Find a signal in their own words before writing.",
    timing: "Nothing is forcing this now. Expect a \"not now\" — and plan the return trip.",
    access: "No reliable route to them. Fix the address or the channel before sending.",
  }[worst.key];
}

/** Feature 12 — the evidence rows, strongest dimension first, so the panel
 *  reads as an argument rather than a table. */
export function explanationRows(detail: FptaDetail | null | undefined): FptaDimension[] {
  return [...(detail?.dimensions ?? [])].sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
}

/** True when the panel should warn that the model did not write these
 *  reasons — the deterministic fallback is honest but terser. */
export function isHeuristicOnly(detail: FptaDetail | null | undefined): boolean {
  return detail?.method === "heuristic";
}
