/** Part 1 Feature 5 — the human review queue, shaped for the UI.
 *  Pure; tested in src/tests/sendReview.test.ts. */

export type TriggerCode = "prior_objection" | "deal_stalled" | "vip_title" | "tone_flag";
export type ReviewStatus = "pending" | "approved" | "rejected";

export interface ReviewTrigger {
  code: TriggerCode;
  label: string;
  detail: string;
}

export interface SendReviewItem {
  id: string;
  message_id: string;
  status: ReviewStatus;
  triggers: ReviewTrigger[];
  subject: string | null;
  body: string | null;
  edited: boolean;
  channel: string | null;
  step_no: number | null;
  message_status: string | null;
  lead: { id: string; full_name: string | null; title: string | null;
          company: string | null; email: string | null } | null;
  decision_note: string | null;
  decided_at: string | null;
  decided_by_user_id: string | null;
  created_at: string | null;
}

/** The API refuses a shorter one — a rejected message is never sent, and the
 *  next person to read the queue needs to know why. */
export const MIN_REJECT_NOTE = 5;

/** Most serious first: an objection is the one that can end a relationship,
 *  a tone flag is the one a reviewer can simply fix. */
const SEVERITY: Record<TriggerCode, number> = {
  prior_objection: 0, deal_stalled: 1, vip_title: 2, tone_flag: 3,
};

export function sortTriggers(triggers: ReviewTrigger[]): ReviewTrigger[] {
  return [...triggers].sort((a, b) =>
    (SEVERITY[a.code] ?? 9) - (SEVERITY[b.code] ?? 9) || a.code.localeCompare(b.code));
}

export function triggerTone(code: TriggerCode): "destructive" | "warning" | "default" {
  if (code === "prior_objection") return "destructive";
  if (code === "deal_stalled" || code === "vip_title") return "warning";
  return "default";
}

/** The headline of a queue row: who, and the single most serious reason. */
export function reviewHeadline(item: SendReviewItem): string {
  const who = item.lead?.full_name ?? item.lead?.email ?? "this prospect";
  const worst = sortTriggers(item.triggers)[0];
  if (!worst) return `Step ${item.step_no ?? "?"} to ${who}`;
  return `${worst.label} — ${who}`;
}

/** "3 days waiting". A queue that does not show its age stops being worked. */
export function waitingFor(item: SendReviewItem, now: Date = new Date()): string {
  if (!item.created_at) return "";
  const ms = now.getTime() - new Date(item.created_at).getTime();
  if (Number.isNaN(ms) || ms < 0) return "";
  const hours = Math.floor(ms / 3_600_000);
  if (hours < 1) return "waiting less than an hour";
  if (hours < 24) return `waiting ${hours} hour${hours === 1 ? "" : "s"}`;
  const days = Math.floor(hours / 24);
  return `waiting ${days} day${days === 1 ? "" : "s"}`;
}

/** True once a held message has waited long enough that sending it would be
 *  odd — the copy referenced "this week" and it is now next week. */
export function isStale(item: SendReviewItem, now: Date = new Date()): boolean {
  if (!item.created_at || item.status !== "pending") return false;
  return now.getTime() - new Date(item.created_at).getTime() > 3 * 24 * 3_600_000;
}

export function canDecide(item: SendReviewItem): boolean {
  return item.status === "pending";
}

export function rejectNoteError(note: string): string | null {
  return note.trim().length < MIN_REJECT_NOTE
    ? `Say why in at least ${MIN_REJECT_NOTE} characters — this message will never be sent.`
    : null;
}

/** True when the reviewer has changed the copy and approving would send the
 *  edit rather than the original. */
export function hasEdits(item: SendReviewItem, subject: string, body: string): boolean {
  return subject !== (item.subject ?? "") || body !== (item.body ?? "");
}
