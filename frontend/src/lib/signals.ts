/** F02 Signal Radar — dated "why now" signals, shaped for the UI.
 *  Pure; tested in src/tests/signals.test.ts. */

export type SignalStatus = "fresh" | "aging" | "expired";

export interface LeadSignal {
  id: string;
  type: string;
  type_label: string;
  source: string;
  source_label: string;
  source_name: string | null;
  source_url: string | null;
  title: string;
  excerpt: string | null;
  observed_at: string;
  expires_at: string;
  first_seen_at: string;
  age_days: number;
  confidence: number;
  freshness: number;
  score: number;
  status: SignalStatus;
  citable: boolean;
  not_citable_reason: string | null;
}

export interface LeadSignals {
  lead_id: string;
  /** false = the admin has Signal Radar turned off; the panel renders nothing. */
  enabled: boolean;
  claim_verification: boolean | null;
  signals: LeadSignal[];
  top: LeadSignal | null;
}

export function statusTone(status: SignalStatus): "success" | "warning" | "default" {
  if (status === "fresh") return "success";
  if (status === "aging") return "warning";
  return "default";
}

export function statusLabel(status: SignalStatus): string {
  return status === "fresh" ? "Fresh" : status === "aging" ? "Aging" : "Expired";
}

/** "today" / "3 days ago" / "about 2 months ago" — the age is the point. */
export function ageLabel(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 31) return `${days} days ago`;
  const months = Math.round(days / 30);
  return `about ${months} month${months === 1 ? "" : "s"} ago`;
}

/** Only http(s) links are ever rendered as links. A stored URL is data from
 *  outside this system; `javascript:` and friends must never become an href. */
export function safeHref(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
  } catch {
    return null;
  }
}

export function sourceText(signal: LeadSignal): string {
  return signal.source_name && signal.source_name !== signal.source_label
    ? `${signal.source_label} · ${signal.source_name}`
    : signal.source_label;
}

/** The one line at the top of the panel. Says plainly when there is nothing
 *  citable, and why, rather than implying a reason to write that is not there. */
export function signalHeadline(data: LeadSignals | undefined): string {
  if (!data || !data.enabled) return "";
  if (data.signals.length === 0) {
    return "No dated signals on record for this prospect yet.";
  }
  if (data.top) {
    return `Why now: ${data.top.type_label.toLowerCase()} — ${ageLabel(data.top.age_days)}, ` +
      `with a source link. Email may cite it only if the claim check ties the sentence to it.`;
  }
  if (data.claim_verification === false) {
    return "Signals are shown, but none can be cited while claim verification is off.";
  }
  return "No citable signal — each one below says why.";
}

/** Best first, as the API sends them; kept stable for equal scores. */
export function orderSignals(signals: LeadSignal[]): LeadSignal[] {
  return [...signals].sort((a, b) => b.score - a.score
    || Date.parse(b.observed_at) - Date.parse(a.observed_at));
}
