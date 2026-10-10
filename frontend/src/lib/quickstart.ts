/** F06 Quickstart — website URL + one-line offer → review-only first drafts.
 *  Pure helpers; tested in src/tests/quickstart.test.ts.
 *
 *  The server is the authority on every rule here (URL safety, offer length).
 *  These only give the user an answer before a round trip. */

export type QuickstartStatus =
  | "queued" | "fetching" | "extracting" | "sourcing" | "drafting" | "ready" | "failed";

export interface QuickstartConfig {
  enabled: boolean;
  lead_target: number;
  budget_usd: number;
  label: string;
}

export interface QuickstartDraft {
  id: string;
  run_id: string;
  status: "draft" | "discarded";
  label: string;
  subject: string;
  body: string;
  claims_changed: number;
  lead: { id: string; full_name: string | null; title: string | null;
          company: string | null; email: string | null } | null;
  created_at: string | null;
}

export interface QuickstartRun {
  id: string;
  status: QuickstartStatus;
  error: string | null;
  website_url: string;
  offer: string;
  product_id: string;
  strategy_id: string;
  strategy_status: string | null;
  icp: Record<string, string[]> | null;
  website: { final_url?: string; title?: string; truncated?: boolean } | null;
  lead_target: number;
  budget_usd: number | null;
  spent_usd: number;
  detail: Record<string, unknown>;
  batch: { id: string; stage: string; error: string | null; requested: number } | null;
  superseded: boolean;
  label: string;
  review_only: true;
  created_at: string | null;
  first_draft_at: string | null;
  ready_at: string | null;
  superseded_at: string | null;
  seconds_to_first_draft: number | null;
  drafts?: QuickstartDraft[];
}

export const MIN_OFFER = 10;
export const MAX_OFFER = 300;

/** The stepper, in order. `failed` is not a step — it is shown as an error. */
export const STAGES: { status: QuickstartStatus; label: string }[] = [
  { status: "fetching", label: "Reading your website" },
  { status: "extracting", label: "Working out who buys" },
  { status: "sourcing", label: "Finding and verifying leads" },
  { status: "drafting", label: "Writing drafts" },
  { status: "ready", label: "Ready to review" },
];

/** Index of the current stage in STAGES; -1 before the first (queued). */
export function stageIndex(status: QuickstartStatus): number {
  return STAGES.findIndex((s) => s.status === status);
}

export function isInProgress(status: QuickstartStatus): boolean {
  return status !== "ready" && status !== "failed";
}

/** Mirrors the server's normalisation for display: bare host → https://,
 *  http:// → https://. Returns null for something that is plainly not a
 *  web address. The server re-checks everything (incl. private addresses). */
export function normalizeWebsite(input: string): string | null {
  let value = input.trim();
  if (!value || /\s/.test(value)) return null;
  if (!value.includes("://")) value = `https://${value}`;
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (url.protocol === "http:") url.protocol = "https:";
  if (url.protocol !== "https:") return null;
  if (url.username || url.password) return null;
  if (url.port && url.port !== "443") return null;
  if (!url.hostname.includes(".")) return null;
  url.hash = "";
  return url.toString();
}

export function offerError(offer: string): string | null {
  const folded = offer.split(/\s+/).filter(Boolean).join(" ");
  if (folded.length < MIN_OFFER) return `Describe your offer in one line (at least ${MIN_OFFER} characters).`;
  if (folded.length > MAX_OFFER) return `Keep it to one line (${MAX_OFFER} characters at most).`;
  return null;
}

/** "4m 05s", "52s", "1h 02m". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return "—";
  }
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}m`;
}

/** Drafts worth showing first: not discarded, then in the order written. */
export function visibleDrafts(drafts: QuickstartDraft[] | undefined, showDiscarded = false): QuickstartDraft[] {
  return (drafts ?? []).filter((d) => showDiscarded || d.status !== "discarded");
}

/** One line for the ICP card: "Owner, Operations Manager · fire protection". */
export function icpSummary(icp: Record<string, string[]> | null | undefined): string {
  if (!icp) return "";
  const parts = [icp.titles, icp.industries, icp.locations]
    .map((list) => (list ?? []).slice(0, 3).join(", "))
    .filter(Boolean);
  return parts.join(" · ");
}
