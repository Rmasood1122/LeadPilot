/** Part 1 Feature 7 — dated return visits, shaped for the UI.
 *  Pure; tested in src/tests/reengagementMemory.test.ts. */

import type { ReasonKind, ReengagementPlan } from "./api/reengagement";

/** Required, and long enough to be a reason rather than a shrug — the API
 *  enforces the same minimum. */
export const MIN_CANCEL_REASON = 3;

export function reasonTone(kind: ReasonKind | null): "warning" | "destructive" | "default" {
  if (kind === "contract") return "destructive";   // the longest wait
  if (kind === "budget" || kind === "priority") return "warning";
  return "default";
}

/** "in 12 days" / "today" / "3 days overdue". A promise whose age is
 *  invisible is a promise nobody keeps. */
export function dueLabel(plan: ReengagementPlan, now: Date = new Date()): string {
  if (!plan.due_at) return "";
  const days = Math.round(
    (new Date(plan.due_at).getTime() - now.getTime()) / 86_400_000);
  if (Number.isNaN(days)) return "";
  if (days === 0) return "today";
  if (days > 0) return days === 1 ? "tomorrow" : `in ${days} days`;
  const overdue = Math.abs(days);
  return overdue === 1 ? "1 day overdue" : `${overdue} days overdue`;
}

export function isDue(plan: ReengagementPlan, now: Date = new Date()): boolean {
  if (plan.status === "cancelled" || plan.status === "sent") return false;
  return Boolean(plan.due_at) && new Date(plan.due_at as string).getTime() <= now.getTime();
}

/** The line that explains WHY this date, so nobody has to trust it blindly. */
export function whyThisDate(plan: ReengagementPlan): string {
  if (plan.date_from_prospect && plan.stated_return_on) {
    return `They asked us to come back on ${plan.stated_return_on}.`;
  }
  if (plan.interval_days) {
    return `No date given — ${plan.interval_days} days from their reply, `
      + `the usual wait for "${plan.reason_label.toLowerCase()}".`;
  }
  return "No date given.";
}

/** The opening line the return message should use. Shown so a person can
 *  sanity-check it before it goes, and so they can write it themselves. */
export function suggestedOpener(plan: ReengagementPlan): string {
  const who = plan.lead?.full_name?.split(" ")[0] ?? "there";
  if (plan.reason_text) {
    return `Hi ${who} — when we spoke you said ${plan.reason_text}. Has that changed?`;
  }
  return `Hi ${who} — you asked me to come back around now. Is this a better time?`;
}

export function statusTone(status: ReengagementPlan["status"]):
  "success" | "warning" | "destructive" | "default" {
  if (status === "sent") return "success";
  if (status === "due") return "warning";
  if (status === "cancelled") return "destructive";
  return "default";
}

/** Soonest first, and anything already overdue at the very top. */
export function sortPlans(plans: ReengagementPlan[], now: Date = new Date()):
  ReengagementPlan[] {
  return [...plans].sort((a, b) => {
    const overdue = Number(isDue(b, now)) - Number(isDue(a, now));
    if (overdue) return overdue;
    return (a.due_at ?? "").localeCompare(b.due_at ?? "");
  });
}

export function cancelReasonError(reason: string): string | null {
  return reason.trim().length < MIN_CANCEL_REASON
    ? `Say why in at least ${MIN_CANCEL_REASON} characters.`
    : null;
}
