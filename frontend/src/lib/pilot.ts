/** F09 — 30-Day Pilot Mode: pure helpers (no React, no fetching). Tested in
 *  tests/pilot.test.ts. Money is integer cents on the wire; the form takes
 *  currency units and converts here, in one place. */

export type CriterionKind = "min" | "max";
export type CriterionUnit = "count" | "money";
export type CriterionStatus = "met" | "not_met" | "not_comparable";
export type PilotExportFormat = "pdf" | "csv";
export type PilotExportView = "verdict" | "campaigns";

export interface CriterionSpec {
  key: string;
  label: string;
  kind: CriterionKind;
  unit: CriterionUnit;
  min_value: number;
  max_value: number;
  default_selected: boolean;
}

export interface PilotTemplate {
  pilot_days: number;
  scorecard_after_days: number[];
  criteria: CriterionSpec[];
  billing_statement: string;
}

export interface CriterionResult {
  key: string;
  label: string;
  kind: CriterionKind;
  unit: CriterionUnit;
  metric: string;
  target: number;
  actual: number | null;
  status: CriterionStatus;
  met: boolean;
  note: string;
}

export interface Evaluation {
  criteria: CriterionResult[];
  met_count: number;
  criteria_count: number;
  outcome: "met" | "not_met";
  currency: string;
  ledger_currency: string;
}

/** The aggregate F08 figures a pilot shows (a subset of the ledger totals). */
export interface PilotFigures {
  sends: number;
  qualified_conversations: number;
  meetings_booked: number;
  meetings_held: number;
  total_cost_cents: number;
  cost_per_qualified_conversation_cents: number | null;
  cost_per_meeting_booked_cents: number | null;
  cost_per_meeting_held_cents: number | null;
}

export interface Verdict extends Evaluation {
  version: string;
  computed_at: string;
  date_from: string;
  date_to: string;
  end_reason: "completed" | "ended_early";
  plan_at_start: string | null;
  plan_at_end: string | null;
  billing_statement: string;
  ledger: { currency: string; totals: PilotFigures; campaigns: unknown[] };
}

export type PilotPhase = "active" | "verdict_pending" | "ended";

export interface Pilot {
  id: string;
  status: "active" | "ended";
  /** verdict_pending: the 30 days are over, the numbers become final (and the
   *  verdict is frozen by the sweep) at verdict_final_at. */
  phase: PilotPhase;
  verdict_final_at: string | null;
  start_date: string;
  end_date: string;
  started_at: string;
  ends_at: string;
  day: number | null;
  pilot_days: number;
  criteria: { key: string; label: string; kind: CriterionKind; unit: CriterionUnit; target: number }[];
  currency: string;
  strategy_ids: string[] | null;
  scorecard_emails: boolean;
  plan_at_start: string | null;
  plan_at_end: string | null;
  ended_at: string | null;
  end_reason: "completed" | "ended_early" | null;
  exported_at: string | null;
  export_available: boolean;
  verdict: Verdict | null;
  scorecards: { week: number; status: "sending" | "sent" | "failed"; sent_at: string | null }[];
  billing_statement: string;
  progress?: Evaluation & { date_from: string; date_to: string; totals: PilotFigures };
}

export interface PilotStartBody {
  criteria: Record<string, number>;
  strategy_ids: string[] | null;
  scorecard_emails: boolean;
}

/** One row of the setup form: ticked or not, and the raw text typed. */
export interface CriterionInput {
  selected: boolean;
  value: string;
}

export type CriteriaForm = Record<string, CriterionInput>;

export const DISABLED_STATUS = 409;

export function isDisabledError(error: unknown): boolean {
  return typeof error === "object" && error !== null
    && (error as { status?: number }).status === DISABLED_STATUS
    && /disabled by the administrator/i.test(String((error as { detail?: string }).detail ?? ""));
}

/** The template's ticks with empty targets: no number is ever pre-filled. */
export function initialForm(template: PilotTemplate): CriteriaForm {
  const form: CriteriaForm = {};
  for (const c of template.criteria) form[c.key] = { selected: c.default_selected, value: "" };
  return form;
}

/** Currency units ("49.5", "1,200") -> integer cents, or null if not a number. */
export function unitsToCents(text: string): number | null {
  const clean = text.replace(/,/g, "").trim();
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  return Math.round(Number(clean) * 100);
}

/** Validate the form and build the request body, or return the first error.
 *  Mirrors the server rules (app/services/pilot_mode.py validate_criteria) so
 *  the person sees the message before the round trip; the server still decides. */
export function buildStartBody(
  template: PilotTemplate,
  form: CriteriaForm,
  options: { strategyIds: string[] | null; scorecardEmails: boolean },
): { body: PilotStartBody } | { error: string } {
  const criteria: Record<string, number> = {};
  for (const spec of template.criteria) {
    const input = form[spec.key];
    if (!input?.selected) continue;
    if (!input.value.trim()) return { error: `${spec.label}: enter a target.` };
    let value: number | null;
    if (spec.unit === "money") {
      value = unitsToCents(input.value);
      if (value === null) return { error: `${spec.label}: enter an amount like 250 or 249.99.` };
    } else {
      const clean = input.value.replace(/,/g, "").trim();
      if (!/^\d+$/.test(clean)) return { error: `${spec.label}: enter a whole number.` };
      value = Number(clean);
    }
    if (value < spec.min_value) return { error: `${spec.label}: the target must be at least 1.` };
    if (value > spec.max_value) return { error: `${spec.label}: the target is too large.` };
    criteria[spec.key] = value;
  }
  if (Object.keys(criteria).length === 0) return { error: "Set at least one success criterion." };
  if (options.strategyIds !== null && options.strategyIds.length === 0) {
    return { error: "Choose at least one campaign, or count all campaigns." };
  }
  return {
    body: { criteria, strategy_ids: options.strategyIds, scorecard_emails: options.scorecardEmails },
  };
}

export function formatTarget(
  c: { kind: CriterionKind; unit: CriterionUnit; target: number },
  money: (cents: number) => string,
): string {
  const value = c.unit === "money" ? money(c.target) : String(c.target);
  return c.kind === "min" ? `at least ${value}` : `at most ${value}`;
}

export function formatActual(
  c: { unit: CriterionUnit; actual: number | null },
  money: (cents: number) => string,
): string {
  if (c.actual === null || c.actual === undefined) return "—";
  return c.unit === "money" ? money(c.actual) : String(c.actual);
}

/** Wording for one criterion: final on the verdict, "so far" while running. */
export function statusLabel(status: CriterionStatus, final: boolean): string {
  if (status === "met") return final ? "Met" : "Met so far";
  if (status === "not_comparable") return "Not comparable";
  return final ? "Not met" : "Not yet";
}

export function statusTone(status: CriterionStatus): "good" | "bad" | "neutral" {
  if (status === "met") return "good";
  return status === "not_met" ? "bad" : "neutral";
}

export function verdictHeadline(v: Pick<Evaluation, "met_count" | "criteria_count" | "outcome">): string {
  const of = `${v.met_count} of ${v.criteria_count} criteria met`;
  return v.outcome === "met" ? `Every criterion met — ${of}.` : `Not every criterion met — ${of}.`;
}

/** "2026-10-02T00:00:00+00:00" -> "2026-10-02 00:00 UTC". */
export function utcStamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 16)} UTC`;
}

export function dayLabel(
  p: Pick<Pilot, "status" | "day" | "pilot_days"> & Partial<Pick<Pilot, "phase" | "verdict_final_at">>,
): string {
  if (p.status !== "active" || p.day === null) return "Ended";
  if (p.phase === "verdict_pending") {
    return p.verdict_final_at
      ? `Verdict pending — final numbers at ${utcStamp(p.verdict_final_at)}`
      : "Verdict pending";
  }
  return `Day ${p.day} of ${p.pilot_days}`;
}

/** The dates a pilot started now would cover: day 1 is today's UTC date and
 *  day 30 is 29 days later (app/services/pilot_mode.py period_for). */
export function pilotDates(now: Date, days = 30): { start: string; end: string } {
  const start = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const end = new Date(start.getTime() + (days - 1) * 86_400_000);
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}

export function endReasonLabel(reason: Pilot["end_reason"]): string {
  if (reason === "ended_early") return "Ended early";
  if (reason === "completed") return "Completed 30 days";
  return "";
}

export function pilotExportPath(id: string, format: PilotExportFormat,
                                view: PilotExportView = "verdict"): string {
  const q = new URLSearchParams({ format });
  if (format === "csv" && view !== "verdict") q.set("view", view);
  return `/pilots/${encodeURIComponent(id)}/export?${q}`;
}

export function pilotExportFilename(startDate: string, format: PilotExportFormat,
                                    view: PilotExportView = "verdict"): string {
  const suffix = format === "csv" && view === "campaigns" ? "-campaigns" : "";
  return `leadpilot-pilot-verdict-${startDate}${suffix}.${format}`;
}
