/** Part 1 Feature 3 — sequence completion, shaped for the UI.
 *  Pure; tested in src/tests/sequenceCompletion.test.ts. */

export type StopCategory =
  | "replied" | "unsubscribed" | "bounced" | "meeting_booked" | "suppressed"
  | "opted_out" | "crm_closed" | "call_outcome" | "system_kill"
  | "all_steps_skipped" | "other";

export interface CompletionReason {
  category: StopCategory;
  label: string;
  count: number;
  authorised: boolean;
}

export interface CompletionMetrics {
  enrolled: number;
  running: number;
  completed: number;
  dropped: number;
  /** Enrolled before the feature shipped: completion is unanswerable. */
  unknown: number;
  finished: number;
  /** null, never 0, when nothing has finished yet. */
  completion_rate: number | null;
  dropped_unauthorised: number;
  reasons: CompletionReason[];
}

export interface StrategyCompletion extends CompletionMetrics {
  strategy_id: string;
  by_sequence: (CompletionMetrics & { sequence_id: string; name: string })[];
}

/** 0.735 -> "74%". A null rate is "—": a campaign where nothing has finished
 *  has no completion rate, and 0% would read as total failure. */
export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

/** The sentence under the headline number. */
export function completionCaption(metrics: CompletionMetrics | null | undefined): string {
  if (!metrics) return "";
  if (!metrics.enrolled) return "Nobody enrolled yet.";
  if (!metrics.finished) {
    return `${metrics.running} still running — nothing has finished yet.`;
  }
  const parts = [`${metrics.completed} of ${metrics.finished} finished sequences ran to the end`];
  if (metrics.running) parts.push(`${metrics.running} still running`);
  if (metrics.unknown) parts.push(`${metrics.unknown} enrolled before this was tracked`);
  return `${parts.join(" · ")}.`;
}

/** The one line that should make somebody act, or null when nothing is wrong.
 *  Deliberately separate from the rate: a 60% completion rate is fine if the
 *  other 40% replied, and alarming if the system dropped them. */
export function guaranteeWarning(metrics: CompletionMetrics | null | undefined): string | null {
  if (!metrics?.dropped_unauthorised) return null;
  const n = metrics.dropped_unauthorised;
  return `${n} prospect${n === 1 ? "" : "s"} stopped early without a decision behind `
    + `${n === 1 ? "it" : "them"}. Open the list and find out why.`;
}

/** Reasons split into the two groups that mean different things, each sorted
 *  by count so the biggest cause is first. */
export function groupedReasons(metrics: CompletionMetrics | null | undefined): {
  decisions: CompletionReason[];
  drops: CompletionReason[];
} {
  const rows = [...(metrics?.reasons ?? [])].sort((a, b) => b.count - a.count);
  return {
    decisions: rows.filter((r) => r.authorised),
    drops: rows.filter((r) => !r.authorised),
  };
}

/** Sequences worth looking at first: worst completion rate, ties broken by
 *  volume. Sequences with nothing finished are excluded — they have no rate. */
export function worstSequences<T extends CompletionMetrics>(rows: T[], limit = 3): T[] {
  return rows
    .filter((row) => row.completion_rate !== null)
    .sort((a, b) =>
      (a.completion_rate as number) - (b.completion_rate as number) || b.finished - a.finished)
    .slice(0, limit);
}
