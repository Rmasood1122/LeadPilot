/** Feature A3 — reply authenticity, shaped for the inbox. Pure; tested in
 *  src/tests/authenticity.test.ts. */

export type AuthenticityKind = "genuine" | "out_of_office" | "auto_responder" | "bot" | "bounce";

export interface Authenticity {
  kind: AuthenticityKind;
  authenticity_score: number | null;
  buyer_intent_score: number | null;
  confidence: number | null;
  signals: string[];
  scored_at: string | null;
}

export interface InboxReply {
  reply_id: string;
  lead: { id: string; full_name: string | null; company: string | null; status: string | null } | null;
  channel: string;
  from_address: string;
  subject: string | null;
  body_preview: string;
  classification: string | null;
  reply_category: string | null;
  received_at: string | null;
  authenticity: Authenticity | null;
}

const KIND_LABELS: Record<AuthenticityKind, string> = {
  genuine: "Genuine reply", out_of_office: "Out of office", auto_responder: "Auto-responder",
  bot: "Bot / no-reply", bounce: "Bounce",
};

export function kindLabel(kind: AuthenticityKind | null | undefined): string {
  return kind ? KIND_LABELS[kind] ?? kind : "Not scored";
}

export function kindTone(kind: AuthenticityKind | null | undefined):
  "success" | "warning" | "destructive" | "default" {
  if (kind === "genuine") return "success";
  if (kind === "out_of_office") return "warning";
  if (kind === "bot" || kind === "bounce" || kind === "auto_responder") return "destructive";
  return "default";
}

/** 0.873 -> "87%"; null -> "—". */
export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}

export type IntentBand = "hot" | "warm" | "cool" | "none";

export function intentBand(a: Authenticity | null | undefined): IntentBand {
  if (!a || a.kind !== "genuine" || a.buyer_intent_score === null) return "none";
  if (a.buyer_intent_score >= 0.75) return "hot";
  if (a.buyer_intent_score >= 0.45) return "warm";
  return "cool";
}

const SIGNAL_TEXT: [RegExp, string][] = [
  [/^header:/, "auto-reply email header"],
  [/^from:/, "no-reply sender"],
  [/^subject:/, "auto-reply subject line"],
  [/^ooo:/, "out-of-office wording"],
  [/^bounce:/, "delivery failure notice"],
  [/^timing:/, "replied within seconds of sending"],
  [/^classifier:/, "AI classifier verdict"],
  [/^body:/, "automated-message wording"],
  [/^intent:meeting$/, "asks to meet"],
  [/^intent:pricing$/, "asks about price"],
  [/^intent:more_info$/, "asks for more detail"],
  [/^intent:interest$/, "says they're interested"],
  [/^intent:question$/, "asks a question"],
];

/** Human reasons, de-duplicated, in the order they were found. */
export function explainSignals(signals: string[]): string[] {
  const out: string[] = [];
  for (const signal of signals) {
    const match = SIGNAL_TEXT.find(([pattern]) => pattern.test(signal));
    const text = match ? match[1] : signal;
    if (!out.includes(text)) out.push(text);
  }
  return out;
}
