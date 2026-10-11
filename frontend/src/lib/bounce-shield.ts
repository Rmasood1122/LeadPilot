/** F01 — Waterfall Enrichment + Bounce Shield, shaped for the UI.
 *  Pure; tested in src/tests/bounceShield.test.ts. */

export type Verdict = "valid" | "catch_all" | "invalid" | "unknown";
export type Tone = "default" | "success" | "warning" | "destructive";

export interface VerdictRecord {
  verdict: Verdict;
  provider: string | null;
  verifier: string | null;
  score: number | null;
  legacy_status: string | null;
  claimed_status: string | null;
  checked_at: string | null;
}

export interface OverrideRecord {
  by: string | null;
  at: string;
  reason: string;
  verdict_at_override: Verdict | null;
}

export interface Attempt {
  id: string;
  step: string;
  provider: string;
  operation: "find_email" | "verify";
  outcome: string;
  cached: boolean;
  cost_units: number;
  claimed_status: string | null;
  email_domain: string | null;
  created_at: string | null;
}

export interface ShieldSettings {
  enabled: boolean;
  waterfall_enabled: boolean;
  catch_all_policy: "block" | "allow";
  max_age_days: number;
}

export interface EmailVerdict {
  lead_id: string;
  email: string | null;
  verdict: VerdictRecord | null;
  verdict_is_stale_address: boolean;
  override: OverrideRecord | null;
  send_decision: {
    shield_enabled: boolean;
    allowed: boolean;
    would_allow: boolean;
    tag: string | null;
    reason: string | null;
  };
  attempts: Attempt[];
  settings: ShieldSettings;
  released_messages?: number;
  cached?: boolean;
}

const LABELS: Record<Verdict, string> = {
  valid: "Verified valid",
  catch_all: "Catch-all domain",
  invalid: "Undeliverable",
  unknown: "Could not confirm",
};

const TONES: Record<Verdict, Tone> = {
  valid: "success",
  catch_all: "warning",
  invalid: "destructive",
  unknown: "warning",
};

export function verdictLabel(data: EmailVerdict | undefined): string {
  if (!data?.email) return "No email address";
  if (data.verdict_is_stale_address) return "Address changed since verification";
  if (!data.verdict) return "Not verified";
  return LABELS[data.verdict.verdict] ?? data.verdict.verdict;
}

export function verdictTone(data: EmailVerdict | undefined): Tone {
  if (!data?.verdict || data.verdict_is_stale_address) return "default";
  return TONES[data.verdict.verdict] ?? "default";
}

/** One line: will the next email to this person go out, and if not, why. */
export function sendDecisionText(data: EmailVerdict | undefined): string {
  if (!data) return "";
  const d = data.send_decision;
  if (!d.shield_enabled) {
    return d.would_allow
      ? "Bounce Shield is off. This address would pass it."
      : `Bounce Shield is off. If it were on, email would be held: ${d.reason ?? "not verified"}.`;
  }
  if (d.allowed) {
    return d.tag === "override"
      ? "Email will send: a manager allowed this address."
      : "Email will send: the address is verified.";
  }
  return `Email is held: ${d.reason ?? "not verified"}.`;
}

/** Override is offered only where it can help: the shield is on, sending is
 *  held, there is an address, and it was not verified undeliverable. */
export function canOverride(data: EmailVerdict | undefined): boolean {
  if (!data?.email || !data.send_decision.shield_enabled) return false;
  if (data.override) return false;
  if (data.verdict && !data.verdict_is_stale_address && data.verdict.verdict === "invalid") {
    return false;
  }
  return !data.send_decision.allowed;
}

export function canRefresh(data: EmailVerdict | undefined): boolean {
  return !!data?.email && (data.settings.enabled || data.settings.waterfall_enabled);
}

/** Hide the panel entirely when the feature is off and there is nothing to show. */
export function panelVisible(data: EmailVerdict | undefined): boolean {
  if (!data) return false;
  return data.settings.enabled || data.settings.waterfall_enabled
    || !!data.verdict || data.attempts.length > 0;
}

export function attemptText(a: Attempt): string {
  const what = a.operation === "verify" ? "verified" : "searched";
  const cost = a.cached ? "cache hit, no charge" : `${a.cost_units} unit${a.cost_units === 1 ? "" : "s"}`;
  return `${a.provider} ${what}: ${a.outcome.replace("_", " ")} (${cost})`;
}

export function totalCostUnits(attempts: Attempt[]): number {
  return attempts.reduce((sum, a) => sum + (a.cached ? 0 : a.cost_units), 0);
}
