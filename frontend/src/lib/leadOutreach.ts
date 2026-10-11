/** Pure rules for the "Find leads" and "Create sequence and launch" panels.
 *  Kept free of React so the contract is unit-testable. The server is always
 *  the real gate; these only decide what the screen offers. */
import { ApiError, tooManyRequestsMessage } from "@/lib/api/client";
import type { SequenceStepInput } from "@/lib/api/outreach";
import type { LeadOut, StrategyOut } from "@/lib/api/types";

/** Largest batch the screen will request in one click. Each lead spends paid
 *  credits; the server applies its own, separate ceiling. */
export const MAX_UI_LEADS = 25;
export const DEFAULT_SOURCE_LEADS = 5;

/** Statuses where a lead is still moving through source -> enrich -> verify. */
const IN_PROGRESS = ["sourced", "enriched", "email_found"] as const;

export function canSourceLeads(status: StrategyOut["status"]): boolean {
  return status === "verified";
}

/** null = invalid. Whole numbers from 1 to MAX_UI_LEADS only. */
export function parseMaxLeads(raw: string): number | null {
  if (!/^\d+$/.test(raw.trim())) return null;
  const n = Number(raw);
  return n >= 1 && n <= MAX_UI_LEADS ? n : null;
}

export function sourcingProgress(leads: LeadOut[]): {
  total: number;
  running: boolean;
  counts: Record<string, number>;
} {
  const counts: Record<string, number> = {};
  for (const l of leads) counts[l.status] = (counts[l.status] ?? 0) + 1;
  const running = leads.some((l) => (IN_PROGRESS as readonly string[]).includes(l.status));
  return { total: leads.length, running, counts };
}

/** The leads a launch would email: verified, with an address on file. */
export function contactableLeads(leads: LeadOut[]): LeadOut[] {
  return leads.filter((l) => l.status === "verified" && !!l.email);
}

export function buildSequenceSteps(input: {
  openingBrief: string;
  followUpBrief: string;
  followUpDays: number;
}): SequenceStepInput[] {
  const steps: SequenceStepInput[] = [
    { step_no: 1, template: input.openingBrief.trim(), delay_days: 0 },
  ];
  const follow = input.followUpBrief.trim();
  if (follow) steps.push({ step_no: 2, template: follow, delay_days: input.followUpDays });
  return steps;
}

export function canLaunchSequence(input: {
  status: StrategyOut["status"];
  contactable: number;
  openingBrief: string;
  confirmed: boolean;
}): boolean {
  return (
    input.status === "verified" &&
    input.contactable > 0 &&
    input.openingBrief.trim().length > 0 &&
    input.confirmed
  );
}

export function sourceErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return "Could not start lead sourcing. Check your connection and try again.";
  }
  if (err.status === 429) {
    return tooManyRequestsMessage(err, "Too many requests. Wait a few minutes and try again.");
  }
  if (err.status === 409) return err.detail || "This strategy cannot source leads right now.";
  if (err.status === 404) return "This strategy no longer exists.";
  return err.detail || "Could not start lead sourcing.";
}

export function launchErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return "Could not launch. Check your connection and try again.";
  }
  if (err.status === 403 && err.detail === "PHONE_NOT_VERIFIED") {
    return "Your phone number is not verified, so outreach is blocked on this account.";
  }
  if (err.status === 429) {
    return tooManyRequestsMessage(err, "Too many requests. Wait a few minutes and try again.");
  }
  if (err.status === 409 || err.status === 422) {
    return err.detail || "The server refused this launch.";
  }
  return err.detail || "Could not launch the sequence.";
}
