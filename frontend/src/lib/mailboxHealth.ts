/** Part 1 Feature 4 — per-mailbox health, shaped for the settings page.
 *  Pure; tested in src/tests/mailboxHealth.test.ts. */

import type { MailboxBand, MailboxHealth, MailboxState } from "./api/trust";

export function stateLabel(state: MailboxState): string {
  return { healthy: "Sending normally", throttled: "Throttled", paused: "Paused" }[state];
}

export function stateTone(state: MailboxState): "success" | "warning" | "destructive" {
  return state === "healthy" ? "success" : state === "throttled" ? "warning" : "destructive";
}

export function bandTone(band: MailboxBand): "success" | "warning" | "destructive" | "default" {
  return { good: "success", at_risk: "warning", bad: "destructive",
           unchecked: "default" }[band] as "success" | "warning" | "destructive" | "default";
}

/** "82" or "—". Never "0" for a mailbox nothing has checked. */
export function scoreText(score: number | null | undefined): string {
  return score === null || score === undefined ? "—" : String(score);
}

/** 0.0032 -> "0.32%". Rates below a hundredth of a percent still read as a
 *  number, because 0.05% is the difference between fine and a problem. */
export function rateText(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return "—";
  return `${(rate * 100).toFixed(2)}%`;
}

/** The one line under a mailbox saying what is happening to its sending. */
export function throttleExplanation(mailbox: MailboxHealth): string | null {
  if (mailbox.state === "paused") {
    return "Sending is paused. Queued messages are held, not cancelled — they go out "
      + "when you resume this mailbox.";
  }
  if (mailbox.state === "throttled") {
    const cap = mailbox.throttle_cap;
    const normal = mailbox.daily_cap;
    const detail = cap !== null && normal !== null
      ? ` Today's limit is ${cap} instead of ${normal}.`
      : "";
    return `Sending is slowed while health recovers.${detail}`;
  }
  return null;
}

/** The DNS records that are missing, named — a fix list, not a score. */
export function authGaps(mailbox: MailboxHealth): string[] {
  const gaps: string[] = [];
  if (mailbox.auth.spf === false) gaps.push("SPF");
  if (mailbox.auth.dkim === false) gaps.push("DKIM");
  if (mailbox.auth.dmarc === false) gaps.push("DMARC");
  else if (mailbox.auth.dmarc_policy === "none") gaps.push("DMARC is p=none");
  return gaps;
}

/** Mailboxes needing attention first, then by score. Unchecked ones sort last
 *  — they are not evidence of a problem. */
export function sortForDisplay(mailboxes: MailboxHealth[]): MailboxHealth[] {
  const rank: Record<MailboxState, number> = { paused: 0, throttled: 1, healthy: 2 };
  return [...mailboxes].sort((a, b) =>
    rank[a.state] - rank[b.state]
    || (a.score ?? 101) - (b.score ?? 101)
    || (a.address ?? "").localeCompare(b.address ?? ""));
}

/** The banner at the top of the card, or null when everything is fine. */
export function fleetWarning(mailboxes: MailboxHealth[]): string | null {
  const paused = mailboxes.filter((mb) => mb.state === "paused").length;
  const throttled = mailboxes.filter((mb) => mb.state === "throttled").length;
  if (!paused && !throttled) return null;
  const parts: string[] = [];
  if (paused) parts.push(`${paused} mailbox${paused === 1 ? "" : "es"} paused`);
  if (throttled) parts.push(`${throttled} throttled`);
  return `${parts.join(", ")} — outreach is going out slower than planned.`;
}
