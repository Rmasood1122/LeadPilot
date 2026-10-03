/** Part 1 Feature 10 — data provenance tags, shaped for the UI.
 *  Pure; tested in src/tests/provenance.test.ts. */

export type StalenessBand = "fresh" | "stale" | "very_stale" | "unknown";

export interface ProvenanceItem {
  field: string;
  label: string;
  source: string;
  source_label: string;
  source_note: string;
  confidence: number | null;
  observed_at: string | null;
  staleness: { days: number | null; band: StalenessBand };
  detail: string | null;
  value: string | null;
}

export interface LeadProvenance {
  lead_id: string;
  /** false = nothing was ever recorded, which is NOT "unknown source". */
  tracked: boolean;
  updated_at: string | null;
  items: ProvenanceItem[];
  weakest: ProvenanceItem | null;
  stale_count: number;
}

/** Below this, a field is worth double-checking before building a message on
 *  it. Matches the gap between a provider's data and a guess. */
export const TRUST_FLOOR = 0.5;

export function confidenceTone(confidence: number | null | undefined):
  "success" | "warning" | "destructive" | "default" {
  if (confidence === null || confidence === undefined) return "default";
  if (confidence >= 0.8) return "success";
  if (confidence >= TRUST_FLOOR) return "warning";
  return "destructive";
}

export function stalenessTone(band: StalenessBand):
  "success" | "warning" | "destructive" | "default" {
  if (band === "fresh") return "success";
  if (band === "stale") return "warning";
  if (band === "very_stale") return "destructive";
  return "default";
}

/** "3 months old" / "checked today". A field's age is half the story. */
export function ageLabel(item: ProvenanceItem): string {
  const days = item.staleness.days;
  if (days === null) return "age unknown";
  if (days === 0) return "recorded today";
  if (days < 31) return `${days} day${days === 1 ? "" : "s"} old`;
  const months = Math.round(days / 30);
  if (months < 12) return `${months} month${months === 1 ? "" : "s"} old`;
  const years = Math.round(days / 365);
  return `${years} year${years === 1 ? "" : "s"} old`;
}

/** The whole tooltip, in one string: where it came from, how good that source
 *  is, and how old the fact is — the three things that decide whether to build
 *  a message on it. */
export function hoverText(item: ProvenanceItem): string {
  const confidence = item.confidence === null
    ? "unrated"
    : `${Math.round(item.confidence * 100)}%`;
  return `${item.source_label} · ${confidence} · ${ageLabel(item)} — ${item.source_note}`;
}

/** True when a field should not be quoted back to the prospect without a
 *  check: weak source, or old enough to have changed. */
export function needsChecking(item: ProvenanceItem): boolean {
  if (item.confidence !== null && item.confidence < TRUST_FLOOR) return true;
  return item.staleness.band === "very_stale";
}

/** The line above the list. Says "not recorded" rather than implying the data
 *  came from nowhere. */
export function provenanceHeadline(data: LeadProvenance | null | undefined): string {
  if (!data) return "";
  if (!data.tracked) {
    return "No provenance recorded for this prospect — they were sourced before "
      + "this was tracked.";
  }
  const weak = data.items.filter(needsChecking).length;
  const parts = [`${data.items.length} field${data.items.length === 1 ? "" : "s"} tagged`];
  if (weak) parts.push(`${weak} worth checking`);
  if (data.stale_count) parts.push(`${data.stale_count} over three months old`);
  return `${parts.join(" · ")}.`;
}

/** Fields worth checking first, then the rest as recorded (weakest first from
 *  the API). */
export function flagged(data: LeadProvenance | null | undefined): ProvenanceItem[] {
  return (data?.items ?? []).filter(needsChecking);
}
