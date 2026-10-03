/** Part 2 — the call script, the readiness checklist and roleplay practice,
 *  shaped for the UI. Pure; tested in src/tests/practice.test.ts. */

export interface ScriptObjection {
  objection: string;
  response: string;
}

export interface CallScript {
  opening: string;
  discovery: string[];
  objections: ScriptObjection[];
  close: string;
  notes: string;
}

export interface ScriptResponse {
  brief_id: string;
  script: CallScript;
  /** false = nobody has approved this text yet. */
  edited: boolean;
  edited_at: string | null;
  edited_by_user_id: string | null;
}

export interface ReadinessItem {
  key: string;
  label: string;
  done: boolean;
  detail: string;
  blocking: boolean;
}

export interface Readiness {
  brief_id: string;
  lead_id: string;
  items: ReadinessItem[];
  done: number;
  total: number;
  ready: boolean;
  blocking: string[];
  practice_required: boolean;
  meeting_start_at: string | null;
  minutes_until: number | null;
  headline: string;
}

export type Difficulty = "easy" | "realistic" | "hostile";
export type SessionStatus = "active" | "completed" | "abandoned";

export interface RoleplayTurn {
  turn_no: number;
  role: "seller" | "prospect";
  content: string;
  at: string | null;
}

export interface RoleplayFeedback {
  scores: Record<string, number | null>;
  went_well: string[];
  improve: string[];
  tone_notes: string;
  pacing_notes: string;
  objections_missed: { objection: string; why: string }[];
  one_thing: string;
}

export interface RoleplaySession {
  id: string;
  status: SessionStatus;
  difficulty: Difficulty;
  lead: { id: string; full_name: string | null; company: string | null } | null;
  brief_id: string | null;
  persona: Record<string, unknown> | null;
  objectives: string[];
  turn_count: number;
  max_turns: number;
  scores: Record<string, number | null>;
  feedback: RoleplayFeedback | null;
  error: string | null;
  started_at: string | null;
  ended_at: string | null;
  turns?: RoleplayTurn[];
}

export interface PracticeHistory {
  total: number;
  completed: number;
  items: RoleplaySession[];
  trend: { at: string | null; overall: number | null; discovery: number | null;
           objections: number | null; tone: number | null; close: number | null }[];
  /** null, never 0, when nothing has been scored. */
  average_overall: number | null;
  best_overall: number | null;
}

export const DIFFICULTIES: { value: Difficulty; label: string; note: string }[] = [
  { value: "easy", label: "Warm", note: "Curious, gives ground easily." },
  { value: "realistic", label: "Realistic",
    note: "Busy and sceptical, like someone who took a cold meeting." },
  { value: "hostile", label: "Hostile",
    note: "Short of time and unconvinced. Will end the call." },
];

export const SCORE_LABELS: Record<string, string> = {
  overall: "Overall", discovery: "Discovery", objections: "Objection handling",
  tone: "Tone", close: "Close",
};

/** The empty script, so a component never has to guard every field. */
export function emptyScript(): CallScript {
  return { opening: "", discovery: [], objections: [], close: "", notes: "" };
}

/** True when the script still says only what the model wrote. The UI labels it
 *  "suggested" until a person has touched it, so generated text is never
 *  mistaken for something that was approved. */
export function isSuggested(script: ScriptResponse | null | undefined): boolean {
  return !script?.edited;
}

/** "3 questions · 2 objections" — what the seller is actually walking in with. */
export function scriptSummary(script: CallScript | null | undefined): string {
  if (!script) return "";
  const questions = script.discovery.filter((q) => q.trim()).length;
  const objections = script.objections.filter((o) => o.objection.trim()).length;
  const parts = [
    script.opening.trim() ? "opening ready" : "no opening",
    `${questions} question${questions === 1 ? "" : "s"}`,
    `${objections} objection${objections === 1 ? "" : "s"}`,
    script.close.trim() ? "close ready" : "no close",
  ];
  return parts.join(" · ");
}

/** The parts of a call that are still blank — a to-do list, not a score. */
export function scriptGaps(script: CallScript | null | undefined): string[] {
  if (!script) return [];
  const gaps: string[] = [];
  if (!script.opening.trim()) gaps.push("opening");
  if (!script.discovery.some((q) => q.trim())) gaps.push("discovery questions");
  if (script.objections.filter((o) => o.objection.trim()).length < 3) {
    gaps.push("at least three objections");
  }
  if (!script.close.trim()) gaps.push("close");
  return gaps;
}

export function readinessTone(state: Readiness | null | undefined):
  "success" | "warning" | "destructive" | "default" {
  if (!state) return "default";
  if (!state.ready) return "destructive";
  return state.done === state.total ? "success" : "warning";
}

/** Blocking items first — the rest is optional polish. */
export function sortedItems(state: Readiness | null | undefined): ReadinessItem[] {
  return [...(state?.items ?? [])].sort((a, b) =>
    Number(b.blocking) - Number(a.blocking) || Number(a.done) - Number(b.done));
}

export function difficultyNote(value: Difficulty): string {
  return DIFFICULTIES.find((d) => d.value === value)?.note ?? "";
}

/** "8 of 40 turns" — a rehearsal is bounded, and the UI says by how much. */
export function turnBudget(session: RoleplaySession | null | undefined): string {
  if (!session) return "";
  return `${session.turn_count} of ${session.max_turns} turns`;
}

export function isNearlyOver(session: RoleplaySession | null | undefined): boolean {
  if (!session) return false;
  return session.turn_count >= session.max_turns - 4;
}

/** Whether finishing now would produce feedback. Fewer than two of the
 *  seller's own lines is not a conversation worth scoring. */
export function canBeScored(session: RoleplaySession | null | undefined): boolean {
  const seller = (session?.turns ?? []).filter((t) => t.role === "seller").length;
  return seller >= 2;
}

/** The five scores as rows, in a fixed order, skipping any the coach did not
 *  give rather than rendering them as zero. */
export function scoreRows(scores: Record<string, number | null> | null | undefined) {
  return ["overall", "discovery", "objections", "tone", "close"]
    .map((key) => ({ key, label: SCORE_LABELS[key], value: scores?.[key] ?? null }))
    .filter((row) => row.value !== null);
}

export function scoreTone(value: number | null): "success" | "warning" | "destructive" | "default" {
  if (value === null) return "default";
  if (value >= 75) return "success";
  if (value >= 50) return "warning";
  return "destructive";
}

/** Improvement between the first and last scored session, or null when there
 *  is not enough history to claim one. */
export function improvement(history: PracticeHistory | null | undefined): number | null {
  const scored = (history?.trend ?? []).filter((p) => p.overall !== null);
  if (scored.length < 2) return null;
  return (scored[scored.length - 1].overall as number) - (scored[0].overall as number);
}

/** The line above the history chart. */
export function historyHeadline(history: PracticeHistory | null | undefined): string {
  if (!history || !history.total) return "No practice sessions yet.";
  if (history.average_overall === null) {
    return `${history.total} session${history.total === 1 ? "" : "s"}, none scored yet.`;
  }
  const delta = improvement(history);
  const trend = delta === null ? ""
    : delta > 0 ? ` · up ${delta} points since your first`
      : delta < 0 ? ` · down ${Math.abs(delta)} points since your first`
        : " · level with your first";
  return `${history.completed} scored · averaging ${history.average_overall}${trend}.`;
}
