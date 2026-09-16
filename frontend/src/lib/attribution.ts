/** Part 1 Feature 8 — the attribution ledger, shaped for the UI.
 *  Pure; tested in src/tests/attribution.test.ts. */

export type AttributionMethod = "direct_reply" | "thread_match" | "last_touch" | "none";
export type OutcomeKind = "meeting_booked" | "positive_reply" | "won";

export interface AttributionEntry {
  id: string;
  outcome_kind: OutcomeKind;
  outcome_at: string | null;
  lead: { id: string; full_name: string | null; company: string | null } | null;
  message_id: string | null;
  channel: string | null;
  step_no: number | null;
  message_sent_at: string | null;
  hours_to_outcome: number | null;
  method: AttributionMethod;
  method_label: string;
  confidence: number | null;
  is_certain: boolean;
  evidence: string[];
  subject: string | null;
  body: string | null;
}

export interface AttributionBucket {
  count: number;
  certain: number;
}

export interface AttributionSummary {
  total: number;
  certain: number;
  by_step: (AttributionBucket & { step_no: number })[];
  by_channel: (AttributionBucket & { channel: string })[];
  by_method: { method: AttributionMethod; label: string; count: number }[];
  median_hours_to_outcome: number | null;
}

const OUTCOME_LABELS: Record<OutcomeKind, string> = {
  meeting_booked: "Meeting booked",
  positive_reply: "Positive reply",
  won: "Deal won",
};

export function outcomeLabel(kind: OutcomeKind): string {
  return OUTCOME_LABELS[kind] ?? kind;
}

/** A fact and a guess must never look the same. */
export function methodTone(method: AttributionMethod):
  "success" | "warning" | "default" {
  if (method === "direct_reply") return "success";
  if (method === "thread_match") return "warning";
  return "default";
}

/** "Step 2 · Email" — the credited touch in four words. */
export function touchLabel(entry: AttributionEntry): string {
  if (!entry.message_id) return "No touch to credit";
  const channel = entry.channel
    ? entry.channel[0].toUpperCase() + entry.channel.slice(1)
    : "Unknown channel";
  return entry.step_no ? `Step ${entry.step_no} · ${channel}` : channel;
}

/** "4h later" / "6 days later". How long the message took to work. */
export function gapLabel(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "";
  if (hours < 1) return "within the hour";
  if (hours < 48) return `${Math.round(hours)}h later`;
  const days = Math.round(hours / 24);
  return `${days} days later`;
}

/** The sentence under a ledger row. Says plainly whether this is known or
 *  inferred, because a ledger that hides that will be believed when it should
 *  not be. */
export function certaintyNote(entry: AttributionEntry): string {
  if (entry.is_certain) return "Known — they replied to this message.";
  const pct = entry.confidence === null ? "" : ` (${Math.round(entry.confidence * 100)}% confidence)`;
  if (entry.method === "none") return "Nothing was sent before this outcome.";
  return `Inferred${pct} — ${entry.method_label.toLowerCase()}.`;
}

/** What share of the ledger is actually known rather than guessed. Null when
 *  there is nothing to divide by — never 0%, which would read as "all guesses". */
export function certainShare(summary: AttributionSummary | null | undefined): number | null {
  if (!summary || !summary.total) return null;
  return summary.certain / summary.total;
}

/** The warning above an aggregate built mostly from guesses. */
export function summaryCaveat(summary: AttributionSummary | null | undefined): string | null {
  const share = certainShare(summary);
  if (share === null) return null;
  if (share >= 0.5) return null;
  return `Only ${Math.round(share * 100)}% of these are confirmed by a reply — `
    + "the rest credit the last message sent before the outcome, which is a guess.";
}

/** Steps ranked by how many outcomes they earned, best first. */
export function rankedSteps(summary: AttributionSummary | null | undefined) {
  return [...(summary?.by_step ?? [])].sort((a, b) => b.count - a.count || a.step_no - b.step_no);
}
