/** Feature A7 — the pre-send adversarial review, shaped for the UI.
 *  Pure; tested in src/tests/sequenceReview.test.ts. */

export type Severity = "block" | "warn" | "info";

export interface ReviewFinding {
  id: string;
  step_no: number | null;
  severity: Severity;
  category: "spam" | "tone" | "compliance" | "claim" | "system";
  code: string;
  message: string;
  evidence: string | null;
  source: "rules" | "model";
}

export interface SequenceReview {
  id: string;
  sequence_id: string;
  status: "passed" | "blocked" | "overridden";
  is_current: boolean;
  blocking_count: number;
  warning_count: number;
  reviewer: string;
  findings: ReviewFinding[];
  created_at: string | null;
  override_reason: string | null;
  overridden_at: string | null;
  overridden_by_user_id: string | null;
}

/** The exact 409 detail the enroll/approve gate returns. */
export const REVIEW_BLOCKED = "SEQUENCE_REVIEW_BLOCKED";
export const MIN_OVERRIDE_REASON = 10;

const ORDER: Record<Severity, number> = { block: 0, warn: 1, info: 2 };

/** Blocking first, then by step, then warnings and info. */
export function sortFindings(findings: ReviewFinding[]): ReviewFinding[] {
  return [...findings].sort((a, b) =>
    ORDER[a.severity] - ORDER[b.severity]
    || (a.step_no ?? 0) - (b.step_no ?? 0)
    || a.code.localeCompare(b.code));
}

export function severityTone(severity: Severity): "destructive" | "warning" | "default" {
  return severity === "block" ? "destructive" : severity === "warn" ? "warning" : "default";
}

/** What the header of the panel says. */
export function reviewHeadline(review: SequenceReview | null | undefined): string {
  if (!review) return "Not reviewed yet";
  if (!review.is_current) return "Content changed since the last review";
  if (review.status === "blocked") {
    return `${review.blocking_count} blocking issue${review.blocking_count === 1 ? "" : "s"} — fix or override to launch`;
  }
  if (review.status === "overridden") return "Launched with an override";
  return review.warning_count ? `Ready to launch · ${review.warning_count} warning${review.warning_count === 1 ? "" : "s"}` : "Ready to launch";
}

export function canLaunch(review: SequenceReview | null | undefined): boolean {
  return !!review && review.is_current && review.status !== "blocked";
}

export function overrideReasonError(reason: string): string | null {
  const trimmed = reason.trim();
  return trimmed.length >= MIN_OVERRIDE_REASON
    ? null : `Explain why in at least ${MIN_OVERRIDE_REASON} characters.`;
}
