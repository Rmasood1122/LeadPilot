/** Part 1 Feature 1 — positive reply classification, shaped for the UI.
 *  Pure; tested in src/tests/replyIntent.test.ts. */

export type IntentLabel = "interested" | "neutral" | "objection" | "not_now" | "unsubscribe";

export const INTENT_LABELS: IntentLabel[] = [
  "interested", "neutral", "objection", "not_now", "unsubscribe",
];

export interface ReplyIntent {
  label: IntentLabel | null;
  confidence: number | null;
  reason: string | null;
  source: "model" | "rules" | null;
  at: string | null;
  is_positive: boolean;
}

export interface ReplyQuality {
  sent: number;
  replies: number;
  human_replies: number;
  classified: number;
  unclassified: number;
  /** null, never 0, when nothing has been sent — see the API note. */
  reply_rate: number | null;
  positive_reply_rate: number | null;
  positive_share: number | null;
  breakdown: Record<IntentLabel, number>;
}

const LABELS: Record<IntentLabel, string> = {
  interested: "Interested",
  neutral: "Neutral",
  objection: "Objection",
  not_now: "Not now",
  unsubscribe: "Unsubscribe",
};

export function intentLabel(label: IntentLabel | null | undefined): string {
  return label ? LABELS[label] ?? label : "Not classified";
}

export function intentTone(label: IntentLabel | null | undefined):
  "success" | "warning" | "destructive" | "default" {
  if (label === "interested") return "success";
  if (label === "not_now") return "warning";
  if (label === "objection" || label === "unsubscribe") return "destructive";
  return "default";
}

/** 0.735 -> "74%". A null rate is "—", never "0%": a campaign that has sent
 *  nothing has no reply rate, and charting it as zero reads as failure. */
export function percent(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value * 100)}%`;
}

/** What the campaign header says under the positive reply rate. */
export function qualityCaption(q: ReplyQuality | null | undefined): string {
  if (!q) return "";
  if (!q.sent) return "Nothing sent yet.";
  if (!q.human_replies) return `${q.replies} replies, none from a person yet.`;
  if (q.unclassified) {
    return `${q.classified} of ${q.human_replies} human replies classified · `
      + `${q.unclassified} still to classify`;
  }
  return `${q.classified} human ${q.classified === 1 ? "reply" : "replies"} classified`;
}

/** True when the positive rate is not yet worth reading: too little data, or
 *  most of the replies have no label. Guards against a headline number that
 *  looks like a verdict but is really a sample of two. */
export function qualityIsProvisional(q: ReplyQuality | null | undefined): boolean {
  if (!q || q.positive_reply_rate === null) return true;
  if (q.human_replies < 5) return true;
  return q.classified < q.human_replies / 2;
}

export interface BreakdownRow {
  label: IntentLabel;
  text: string;
  count: number;
  share: number;
}

/** The breakdown as rows, largest first, zero-count labels dropped. */
export function breakdownRows(q: ReplyQuality | null | undefined): BreakdownRow[] {
  if (!q) return [];
  const total = INTENT_LABELS.reduce((sum, label) => sum + (q.breakdown[label] ?? 0), 0);
  return INTENT_LABELS
    .map((label) => ({
      label,
      text: LABELS[label],
      count: q.breakdown[label] ?? 0,
      share: total ? (q.breakdown[label] ?? 0) / total : 0,
    }))
    .filter((row) => row.count > 0)
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}

/** The one-line explanation shown beside a reply's label. */
export function intentExplanation(intent: ReplyIntent | null | undefined): string {
  if (!intent?.label) return "Not classified yet.";
  const confidence = intent.confidence === null ? "" : ` · ${percent(intent.confidence)} confident`;
  const source = intent.source === "rules" ? " · decided by rule" : "";
  return `${intentLabel(intent.label)}${confidence}${source}${intent.reason ? ` — ${intent.reason}` : ""}`;
}
