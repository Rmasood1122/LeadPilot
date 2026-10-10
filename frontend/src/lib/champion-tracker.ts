/** F10 — Champion Tracker + Staleness Check, shaped for the UI.
 *  Pure; tested in src/tests/championTracker.test.ts. */

export type Tone = "default" | "success" | "warning" | "destructive";
export type RoleState = "current" | "confirmed" | "title_changed" | "left" | "disputed";

export interface ChampionAttempt {
  id: string;
  step: string;
  provider: string;
  operation: string;
  outcome: string;
  cached: boolean;
  cost_units: number;
  created_at: string | null;
}

export interface HeldMessage {
  id: string;
  lead_id: string;
  channel: string | null;
  step_no: number;
  status: string;
  reason: string | null;
  scheduled_at: string | null;
  lead?: { full_name: string | null; title: string | null; company: string | null };
}

export interface ChampionMove {
  id: string;
  old_lead_id: string | null;
  new_lead_id: string | null;
  new_lead: { id: string; full_name: string | null; title: string | null;
              company: string | null; email: string | null; status: string | null } | null;
  champion_kind: "positive_reply" | "customer" | null;
  from_company: string | null;
  from_title: string | null;
  to_company: string | null;
  to_title: string | null;
  to_domain: string | null;
  trigger: string;
  outcome: string;
  detail: string | null;
  detected_at: string | null;
  dismissed_at: string | null;
  dismiss_reason: string | null;
}

export interface RoleCheck {
  lead_id: string;
  enabled: boolean;
  title: string | null;
  company: string | null;
  state: RoleState | null;
  last_outcome: string | null;
  observed_title: string | null;
  observed_company: string | null;
  checked_at: string | null;
  attempted_at: string | null;
  retry_after: string | null;
  confirmed_by: string | null;
  observed_at: string | null;
  age_days: number | null;
  champion_kind: "positive_reply" | "customer" | null;
  previous: { from_company: string | null; from_title: string | null;
              previous_lead_id: string | null; move_id: string | null } | null;
  send_decision: {
    would_send: boolean;
    blocked: boolean;
    held: boolean;
    reason: string | null;
    would_hold_if_enabled?: string | null;
  };
  held_messages: HeldMessage[];
  move: ChampionMove | null;
  attempts: ChampionAttempt[];
  settings: { enabled: boolean; staleness_days: number; run_cap: number;
              account_monthly_units: number };
  released_messages?: number;
  adopted_title?: string | null;
  result?: { outcome: string; released: number; move_id?: string };
}

/** Required, and long enough to be a reason — the API enforces the same. */
export const MIN_REASON = 5;

export function reasonError(reason: string): string | null {
  return reason.trim().length < MIN_REASON
    ? `Say why in at least ${MIN_REASON} characters.`
    : null;
}

const STATE_LABELS: Record<RoleState, string> = {
  current: "Role confirmed by enrichment",
  confirmed: "Role confirmed by a person",
  title_changed: "Title changed",
  left: "Left the company",
  disputed: "Job change disputed",
};

export function stateLabel(data: RoleCheck | undefined): string {
  if (!data) return "";
  if (data.move && !data.move.dismissed_at) return STATE_LABELS.left;
  if (data.state) return STATE_LABELS[data.state] ?? data.state;
  return "Not checked yet";
}

export function stateTone(data: RoleCheck | undefined): Tone {
  if (!data) return "default";
  if (data.move && !data.move.dismissed_at) return "destructive";
  if (data.state === "title_changed" || data.state === "disputed") return "warning";
  if (data.state === "current" || data.state === "confirmed") return "success";
  return "default";
}

/** One line: will the next message to this person go out, and if not, why. */
export function decisionText(data: RoleCheck | undefined): string {
  if (!data) return "";
  const d = data.send_decision;
  if (d.blocked) return `Messages are blocked: ${d.reason ?? "they left the company"}.`;
  if (!data.enabled) {
    return d.would_hold_if_enabled
      ? `Champion tracker is off. If it were on, messages would be held: ${d.would_hold_if_enabled}.`
      : "Champion tracker is off. The role data is fresh enough to pass it.";
  }
  if (d.held) return `Messages are held: ${d.reason ?? "the role needs re-verification"}.`;
  return "Messages will send: the role is fresh.";
}

/** "observed 12 days ago" / "observed today" / "" */
export function ageText(data: RoleCheck | undefined): string {
  if (!data || data.age_days === null || data.age_days === undefined) return "";
  if (data.age_days === 0) return "role observed today";
  const limit = data.settings.staleness_days;
  const days = data.age_days === 1 ? "1 day" : `${data.age_days} days`;
  return `role observed ${days} ago (limit ${limit})`;
}

/** Re-verify only helps while the feature is on and nobody has left. */
export function canRefresh(data: RoleCheck | undefined): boolean {
  return !!data?.enabled && !(data.move && !data.move.dismissed_at);
}

/** Confirm is for a held prospect who has not been recorded as gone. */
export function canConfirm(data: RoleCheck | undefined): boolean {
  if (!data || (data.move && !data.move.dismissed_at)) return false;
  return data.send_decision.held || data.held_messages.length > 0
    || data.state === "title_changed" || data.state === "disputed";
}

export function canAdoptTitle(data: RoleCheck | undefined): boolean {
  return !!data?.observed_title && data.observed_title !== data.title;
}

/** Hide the panel when the feature is off and nothing was ever recorded. */
export function panelVisible(data: RoleCheck | undefined): boolean {
  if (!data) return false;
  return data.enabled || !!data.move || !!data.state || data.held_messages.length > 0
    || !!data.previous;
}

export function moveText(move: ChampionMove): string {
  const from = [move.from_title, move.from_company].filter(Boolean).join(" at ") || "their old role";
  const to = [move.to_title, move.to_company].filter(Boolean).join(" at ") || "a new company";
  return `Moved from ${from} to ${to}.`;
}

const OUTCOME_TEXT: Record<string, string> = {
  lead_created: "A re-engagement lead was created at the new company.",
  not_champion: "Not a past positive replier or customer — no new lead was created.",
  suppressed: "They opted out before — nothing was created, and the new address is suppressed.",
  excluded: "The new company or the person is on your exclusion lists — nothing was created.",
  existing_lead: "They are already a lead at the new company.",
  no_company: "The new company is unknown — nothing was created.",
  pending: "Still being processed.",
};

export function moveOutcomeText(move: ChampionMove): string {
  return OUTCOME_TEXT[move.outcome] ?? move.outcome;
}

export function attemptText(a: ChampionAttempt): string {
  const cost = a.cached ? "cache hit, no charge"
    : `${a.cost_units} unit${a.cost_units === 1 ? "" : "s"}`;
  const what = a.operation === "role_check" ? "role check" : a.operation.replace("_", " ");
  return `${a.provider} ${what}: ${a.outcome.replace(/_/g, " ")} (${cost})`;
}
