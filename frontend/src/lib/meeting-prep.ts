/** Pure helpers for the Meeting Prep tab and the Log Meeting Outcome flow.
 *  Kept out of the components so the rules are unit-tested (see
 *  src/tests/meeting-prep.test.ts) rather than re-derived in JSX. */

import type {
  DraftStatus,
  MeetingOutcomeKind,
  MeetingPrepBrief,
  PrepProfile,
} from "./api/meetingPrep";

export const OUTCOME_OPTIONS: {
  value: MeetingOutcomeKind;
  label: string;
  hint: string;
}[] = [
  { value: "interested", label: "Interested", hint: "Moves to Opportunity; follow-up in 2 days." },
  { value: "needs_follow_up", label: "Needs follow-up", hint: "Moves to Opportunity; follow-up in 3 days." },
  { value: "not_a_fit", label: "Not a fit", hint: "Disqualified; a gracious close, no pitch." },
  { value: "closed_won", label: "Closed won", hint: "Creates a won deal for revenue analytics." },
  { value: "closed_lost", label: "Closed lost", hint: "Recorded as lost; asks one feedback question." },
];

export function outcomeLabel(value: MeetingOutcomeKind): string {
  return OUTCOME_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

export type Tone = "default" | "success" | "warning" | "destructive" | "accent";

/** What to tell the user about their follow-up draft, and how loudly. */
export function draftStatusInfo(
  status: DraftStatus,
  error?: string | null,
): { tone: Tone; message: string; canSend: boolean; canEdit: boolean } {
  switch (status) {
    case "draft_saved":
      return { tone: "success", message: "Saved as a draft in Gmail. Review it, then send.", canSend: true, canEdit: true };
    case "sent":
      return { tone: "success", message: "Sent.", canSend: false, canEdit: false };
    case "not_connected":
      return { tone: "warning", message: "Gmail isn't connected. Connect it in Settings, or copy the email below.", canSend: false, canEdit: true };
    case "reauth_required":
      return { tone: "warning", message: "Reconnect Gmail in Settings to allow saving drafts. The email text is kept below.", canSend: false, canEdit: true };
    case "suppressed":
      return { tone: "destructive", message: "This contact is on the suppression list. No email will be drafted or sent.", canSend: false, canEdit: false };
    case "no_address":
      return { tone: "warning", message: "This lead has no email address.", canSend: false, canEdit: true };
    case "generation_failed":
      return { tone: "warning", message: "The follow-up couldn't be written. Try Regenerate.", canSend: false, canEdit: false };
    case "failed":
      return { tone: "destructive", message: `Gmail rejected the draft${error ? `: ${error}` : "."}`, canSend: false, canEdit: true };
    default:
      return { tone: "default", message: "No follow-up generated.", canSend: false, canEdit: false };
  }
}

/** Poll while the worker is still writing the brief; stop the moment it
 *  settles, so a failed brief does not poll forever. */
export function isBriefInFlight(brief: Pick<MeetingPrepBrief, "status"> | null | undefined): boolean {
  return !!brief && (brief.status === "pending" || brief.status === "generating");
}

export const PROFILE_FIELDS: { key: keyof PrepProfile; label: string; link?: boolean }[] = [
  { key: "name", label: "Name" },
  { key: "title", label: "Title" },
  { key: "company", label: "Company" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "linkedin_url", label: "LinkedIn", link: true },
  { key: "location", label: "Location" },
  { key: "industry", label: "Industry" },
  { key: "company_size", label: "Company size" },
  { key: "company_website", label: "Website", link: true },
  { key: "founded_year", label: "Founded" },
  { key: "funding", label: "Funding" },
];

/** Profile rows that actually have a value, in display order. */
export function profileRows(profile: PrepProfile | null | undefined) {
  if (!profile) return [];
  return PROFILE_FIELDS.flatMap(({ key, label, link }) => {
    const value = profile[key];
    if (value === null || value === undefined || value === "") return [];
    const text = String(value);
    const href = link ? (/^https?:\/\//.test(text) ? text : `https://${text}`) : undefined;
    return [{ key, label, value: text, href }];
  });
}

/** "Tomorrow 14:00" style label; never throws on a bad date. */
export function meetingWhen(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return "Time not on record";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Time not on record";
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diffDays = Math.round((day.getTime() - today.getTime()) / 86_400_000);
  if (diffDays === 0) return `Today ${time}`;
  if (diffDays === 1) return `Tomorrow ${time}`;
  if (diffDays === -1) return `Yesterday ${time}`;
  return `${date.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" })} ${time}`;
}

/** Parse a user-typed deal value ("4,500.50", "$1200") into a number, or null. */
export function parseDealValue(raw: string): number | null {
  const cleaned = raw.replace(/[^0-9.]/g, "");
  if (!cleaned || (cleaned.match(/\./g) ?? []).length > 1) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) && value >= 0 ? value : null;
}
