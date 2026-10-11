/** Autopilot launch, best time to send and "Why isn't this sending?"
 *  (docs/features/autopilot-launch.md). Pure helpers + types, unit-tested in
 *  src/tests/autopilot.test.ts. The server enforces every rule; these only
 *  decide what the page shows and when a button is enabled. */

export interface LawfulBasis {
  version: string;
  text: string;
  label: string;
  available?: boolean;
}

export interface AutopilotChannel {
  state?: "launched" | "waiting" | "blocked" | "idle";
  reason?: string | null;
  enrolled?: number;
  planned?: boolean;
  fix?: { title: string; fix?: string | null; link?: string | null }[];
}

export interface AutopilotView {
  available: boolean;
  /** Why Autopilot cannot run right now: daily send approval is off, or does
   *  not cover a channel it uses. null when approval covers every channel. */
  approval_gap?: string | null;
  enabled: boolean;
  state: string;
  state_reason: string | null;
  channels: Record<string, AutopilotChannel>;
  confirmed_at: string | null;
  text_version: string | null;
  launched_at: string | null;
  lawful_basis: LawfulBasis;
  can_change?: boolean;
  /** VERIFIED leads from Autopilot's OWN lead searches (never hand-added). */
  eligible_leads?: number;
  /** lead id -> why it can never be contacted ("suppressed", "excluded", ...). */
  unreachable?: Record<string, string>;
  whatsapp_template_id?: string | null;
}

export interface AutopilotOptIn {
  enabled: boolean;
  lawful_basis_confirmed: boolean;
  lawful_basis_text_version: string | null;
}

export interface SendTimeChannel {
  channel: string;
  enabled: boolean;
  basis: string;
  summary: string;
  reason: string;
  priors_note: string | null;
  sending_hours: string;
  fallback_timezone: string;
}

export interface SendTimeView {
  enabled: boolean;
  override: { days: number[]; start: string; end: string } | null;
  timezones: {
    leads: number;
    with_timezone: number;
    sources?: Record<string, number>;
    fallback?: { zone: string; source: string } | null;
  };
  channels: SendTimeChannel[];
}

export interface DiagnosticReason {
  code: string;
  title: string;
  detail: string | null;
  fix: string | null;
  link: string | null;
  count: number | null;
  blocking: boolean;
}

export interface DiagnosticChannel {
  channel: string;
  label: string;
  sending: boolean;
  scheduled: number;
  next_send_at: string | null;
  reasons: DiagnosticReason[];
}

export interface Diagnostics {
  sending: boolean;
  general: DiagnosticReason[];
  channels: DiagnosticChannel[];
  verified_leads_not_enrolled: number;
}

export const STATE_LABELS: Record<string, string> = {
  off: "Off",
  waiting_for_research: "Waiting for research",
  waiting_for_review: "Waiting for your review",
  blocked: "Stopped",
  sourcing: "Finding leads",
  waiting_for_channels: "Waiting for a channel",
  launched: "Running",
  idle: "Nothing to launch",
  paused: "Paused",
};

export function stateLabel(state: string): string {
  return STATE_LABELS[state] ?? state.replace(/_/g, " ");
}

export function stateTone(state: string): "success" | "warning" | "destructive" | "default" {
  if (state === "launched") return "success";
  if (state === "blocked") return "destructive";
  if (state === "waiting_for_review" || state === "waiting_for_channels"
      || state === "paused") return "warning";
  return "default";
}

/** Turning Autopilot ON needs the confirmation ticked for the CURRENT text. */
export function canEnable(confirmed: boolean, basis: LawfulBasis | null | undefined): boolean {
  return confirmed && !!basis?.version && basis.available !== false;
}

/** The body for PUT /strategies/{id}/autopilot or the create-strategy field.
 *  Never sends `enabled: true` without the confirmation. */
export function optInBody(
  enabled: boolean, confirmed: boolean, basis: LawfulBasis | null | undefined,
): AutopilotOptIn {
  const on = enabled && canEnable(confirmed, basis);
  return {
    enabled: on,
    lawful_basis_confirmed: on,
    lawful_basis_text_version: on ? basis!.version : null,
  };
}

/** The intake wizard may launch when Autopilot is either off, or on AND confirmed. */
export function intakeCanLaunch(autopilot: boolean, confirmed: boolean): boolean {
  return !autopilot || confirmed;
}

export const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const TIME = /^([01]\d|2[0-3]):([0-5]\d)$/;

/** Client-side check of an override window, matching the server's rules
 *  (quarter hours, 30 minutes at least). The server has the last word. */
export function overrideError(days: number[], start: string, end: string): string | null {
  if (!days.length) return "Pick at least one day.";
  const s = TIME.exec(start);
  const e = TIME.exec(end);
  if (!s || !e) return "Times are HH:MM, for example 09:30.";
  const sm = Number(s[1]) * 60 + Number(s[2]);
  const em = Number(e[1]) * 60 + Number(e[2]);
  if (sm % 15 || em % 15) return "Use quarter hours (:00, :15, :30, :45).";
  if (em - sm < 30) return "The window must be at least 30 minutes long.";
  return null;
}

/** Blocking reasons first, then the rest; the general ones before channels. */
export function blockingCount(d: Diagnostics): number {
  return d.general.filter((r) => r.blocking).length
    + d.channels.reduce((n, c) => n + c.reasons.filter((r) => r.blocking).length, 0);
}

const FALLBACK_LABELS: Record<string, string> = {
  strategy_region: "the strategy's target region",
  account: "your account's time zone",
  deployment_default: "the default time zone",
};

/** "3 of 10 lead(s) have no known location; their local time is taken from
 *  ..." -- or null when every lead has its own zone. */
export function timezoneNote(tz: SendTimeView["timezones"]): string | null {
  const guessed = tz.leads - tz.with_timezone;
  if (guessed <= 0 || !tz.fallback) return null;
  const label = FALLBACK_LABELS[tz.fallback.source] ?? "a fallback";
  return `${guessed} of ${tz.leads} lead(s) have no known location; their local time is ` +
    `taken from ${label} (${tz.fallback.zone}).`;
}

export function diagnosticsHeadline(d: Diagnostics): string {
  if (d.sending) return "Sending is set up. Nothing is stopping outreach right now.";
  const n = blockingCount(d);
  return n === 1 ? "1 thing is stopping sends." : `${n} things are stopping sends.`;
}

/** "2 lead(s) Autopilot found cannot be contacted (suppressed: 1, excluded: 1)."
 *  -- or null when every lead it found can be. */
export function unreachableNote(unreachable: Record<string, string> | undefined): string | null {
  const reasons = Object.values(unreachable ?? {});
  if (!reasons.length) return null;
  const counts = new Map<string, number>();
  for (const r of reasons) counts.set(r, (counts.get(r) ?? 0) + 1);
  const parts = [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([r, n]) => `${r}: ${n}`);
  return `${reasons.length} lead(s) Autopilot found cannot be contacted (${parts.join(", ")}).`;
}

/** Only APPROVED templates can be chosen for Autopilot (the server also
 *  requires the opt-out wording). Never a default: the person picks one. */
export function approvedTemplates<T extends { status: string }>(templates: T[]): T[] {
  return templates.filter((t) => t.status === "approved");
}

/** The toast after saving the sending window: the server re-places the
 *  scheduled messages in the background (202, `rescheduling` = how many). */
export function bestTimeSavedMessage(
  view: { override: unknown; rescheduling?: number },
): string {
  if (!view.override) return "Back to the automatic best time.";
  const n = view.rescheduling ?? 0;
  return n > 0
    ? `Saved. ${n} scheduled message(s) are being moved into your window.`
    : "Saved. New messages will go out inside your window.";
}

const SOURCE_LABELS: Record<string, string> = {
  lead_recorded: "the lead's own time zone",
  lead_location: "the lead's country and state",
  ...FALLBACK_LABELS,
};

/** Where each lead's local time comes from, e.g. "7 from the lead's country
 *  and state, 3 from the strategy's target region". The same order the
 *  server resolves it in: lead, strategy region, account, default. */
export function timezoneSources(tz: SendTimeView["timezones"]): string | null {
  const order = ["lead_recorded", "lead_location", "strategy_region", "account",
                 "deployment_default"];
  const entries = Object.entries(tz.sources ?? {}).filter(([, n]) => n > 0)
    .sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]));
  if (!entries.length) return null;
  return entries.map(([src, n]) => `${n} from ${SOURCE_LABELS[src] ?? src}`).join(", ");
}
