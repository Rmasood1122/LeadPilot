/** Pure rules for the "Email contacts" tab of the Network page. The server is
 *  the real gate (plan 402, flag 409, attestation 422, every send check); these
 *  only decide what the screen offers and how it words things. */
import { ApiError } from "@/lib/api/client";
import type { EmailImport, EmailMatch, EmailNetworkMessage } from "@/lib/api/emailNetwork";

export const SUBJECT_MAX = 150;
export const BODY_MAX = 3000;
export const ADD_MAX = 100;

const MB = 1024 * 1024;

/** Which limit applies is decided by the server from the CONTENT; here a
 *  quick, generous pre-check so a 2 GB file is not uploaded for nothing. */
export function checkUploadFile(
  file: { name: string; size: number },
  limits: { mbox_max_bytes: number; contacts_max_bytes: number },
): string | null {
  if (file.size === 0) return "That file is empty.";
  const looksLikeMailbox = /\.(mbox|mbx)$/i.test(file.name) || !/\.(csv|vcf|vcard|txt)$/i.test(file.name);
  const max = looksLikeMailbox ? limits.mbox_max_bytes : limits.contacts_max_bytes;
  if (file.size > max) return `That file is larger than ${Math.floor(max / MB)} MB.`;
  return null;
}

export function importErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 402) return "Your plan does not include the email network. Upgrade to Growth or higher.";
    if (err.status === 413) return err.message || "That file is too large.";
    if ([403, 409, 422, 429].includes(err.status)) return err.message;
  }
  return "Import failed. Try again.";
}

const KIND_LABEL: Record<string, string> = {
  google_csv: "Google Contacts file",
  outlook_csv: "Outlook contacts file",
  csv: "contacts file",
  vcard: "vCard file",
  mbox: "mailbox export",
  gmail_scan: "Gmail scan",
};

export const kindLabel = (kind: string): string => KIND_LABEL[kind] ?? kind;

/** "1,240 people found, 610 excluded: 300 newsletters / automated senders, ..." */
export function importSummary(r: EmailImport): string {
  const n = (x: number) => x.toLocaleString("en-US");
  const people = `${n(r.people_found)} ${r.people_found === 1 ? "person" : "people"} found`;
  const excluded = r.excluded
    ? `, ${n(r.excluded)} excluded: ` +
      r.excluded_by_reason.map((x) => `${n(x.count)} ${x.label}`).join(", ")
    : "";
  const kept = `. ${n(r.added)} added, ${n(r.updated)} updated`;
  const matched = typeof r.matched === "number" ? `; ${n(r.matched)} matches for your products.` : ".";
  return people + excluded + kept + matched;
}

export function scoreLabel(score: number): "Strong" | "Good" | "Possible" {
  return score >= 70 ? "Strong" : score >= 50 ? "Good" : "Possible";
}

export function relationshipBadge(m: Pick<EmailMatch, "two_way" | "sent_to_count" | "received_from_count">): string {
  if (m.two_way) return "Two-way";
  if (m.sent_to_count) return "You wrote";
  if (m.received_from_count) return "They wrote";
  return "Contacts file";
}

export function validateEmail(subject: string, body: string): string | null {
  const s = subject.trim();
  const b = body.trim();
  if (!s) return "Write a subject first.";
  if (s.length > SUBJECT_MAX) return `Keep the subject under ${SUBJECT_MAX} characters.`;
  if (!b) return "Write the email first.";
  if (b.length > BODY_MAX) return `Keep the email under ${BODY_MAX} characters.`;
  return null;
}

/** Only a draft or a saved (not attached) email can be edited and saved. */
export const isEditable = (m: EmailNetworkMessage | undefined): boolean =>
  !!m && (m.status === "draft" || m.status === "approved");
/** A used first email whose campaign message was rejected, cancelled or
 *  failed: nothing went out, so it can be detached and written again. */
export const openerDead = (m: EmailNetworkMessage | undefined): boolean =>
  m?.status === "used" && ["cancelled", "failed"].includes(m.campaign_message_status ?? "");

/** Only SAVED words can be attached to a campaign. A draft never can. */
export const isAttachable = (m: EmailNetworkMessage | undefined): boolean => m?.status === "approved";

export const messageStatusLabel = (m: EmailNetworkMessage): string =>
  m.status === "used"
    ? `Used as the first campaign email${m.campaign_message_status ? ` (${m.campaign_message_status})` : ""}`
    : m.status === "attached"
      ? "Attached to a campaign: sent with every check when the campaign's first email is due"
      : m.status === "approved"
        ? "Saved"
        : "Draft (not saved)";

export function messageErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 402) return "Your plan does not include the email network. Upgrade to Growth or higher.";
    if ([404, 409, 422, 429, 502].includes(err.status)) return err.message;
  }
  return "Something went wrong. Try again.";
}

export function scanLine(scan: EmailImport | null): string | null {
  if (!scan) return null;
  if (scan.status === "queued") return "Gmail scan queued…";
  if (scan.status === "running") {
    return `Scanning Gmail headers… ${scan.messages_scanned.toLocaleString("en-US")} of up to ${(scan.max_messages ?? 5000).toLocaleString("en-US")} messages read.`;
  }
  if (scan.status === "reconnect_required") return scan.error ?? "Reconnect Gmail in Settings, then scan again.";
  if (scan.status === "failed") return scan.error ?? "The scan failed. Try again later.";
  return `Last Gmail scan: ${importSummary(scan)}`;
}

export const scanInProgress = (scan: EmailImport | null): boolean =>
  !!scan && (scan.status === "queued" || scan.status === "running");

export function parseOwnAddresses(text: string): string[] {
  return Array.from(new Set(text.split(/[\s,;]+/).map((x) => x.trim().toLowerCase())
    .filter((x) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(x)))).slice(0, 20);
}

export function lastSeenLabel(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString("en-US", { month: "short", year: "numeric", timeZone: "UTC" });
}
