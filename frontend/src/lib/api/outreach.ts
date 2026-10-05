import { api } from "./client";
import type { SequenceOut } from "./types";

/** One email step. `template` is a messaging brief; the server personalizes it
 *  per lead. */
export interface SequenceStepInput {
  step_no: number;
  template: string;
  delay_days: number;
}

export interface LeadBatch {
  id: string;
  strategy_id: string;
  stage: string;
  requested_leads: number;
}

/** Start sourcing for a VERIFIED strategy. Spends paid Apollo and Hunter
 *  credits, so callers always cap `maxLeads`. The server refuses (409) any
 *  strategy that has not passed verification. */
export function sourceLeads(strategyId: string, maxLeads: number): Promise<LeadBatch> {
  return api(`/strategies/${strategyId}/leads/source`, { body: { max_leads: maxLeads } });
}

export function createSequence(
  strategyId: string,
  input: { name: string; steps: SequenceStepInput[]; bookingUrl?: string },
): Promise<SequenceOut> {
  const body: Record<string, unknown> = {
    name: input.name,
    channel: "email",
    steps: input.steps,
  };
  if (input.bookingUrl) body.booking_url = input.bookingUrl;
  return api(`/strategies/${strategyId}/sequences`, { body });
}

/** Enroll verified leads and schedule their first message. The server applies
 *  its own gates (verified strategy, active campaign, red-team review, phone
 *  proof, manager approval); a refusal comes back as an ApiError. */
export function enrollSequence(
  sequenceId: string,
): Promise<{ enrolled?: number; warning?: string; status?: string }> {
  return api(`/sequences/${sequenceId}/enroll`, { body: { lead_statuses: ["verified"] } });
}
