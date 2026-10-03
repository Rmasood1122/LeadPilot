import { api } from "./client";
import type { ChannelRequirements, ConsentEvent, ConsentKind, LeadConsent } from "../consent";

/** Part 1 Feature 9 — the consent ledger and cross-channel withdrawal. */

export interface ConsentLedgerPage {
  total: number;
  limit: number;
  offset: number;
  items: ConsentEvent[];
}

export interface RequirementsResponse {
  channels: string[];
  regions: { region: string | null; regime: string;
             channels: Record<string, ChannelRequirements> }[];
  note: string;
}

export const getComplianceRequirements = (region?: string) =>
  api<RequirementsResponse>(
    `/compliance/requirements${region ? `?region=${region}` : ""}`);

export function getConsentLedger(
  opts: { leadId?: string; identifier?: string; kind?: ConsentKind; limit?: number } = {},
) {
  const params = new URLSearchParams();
  if (opts.leadId) params.set("lead_id", opts.leadId);
  if (opts.identifier) params.set("identifier", opts.identifier);
  if (opts.kind) params.set("kind", opts.kind);
  params.set("limit", String(opts.limit ?? 200));
  return api<ConsentLedgerPage>(`/compliance/consent?${params.toString()}`);
}

export const getLeadConsent = (leadId: string) =>
  api<LeadConsent>(`/leads/${leadId}/consent`);

/** "Stop contacting me", every channel at once. `body` is an OBJECT — api()
 *  stringifies it itself. */
export const withdrawConsent = (leadId: string, source: string, detail?: string) =>
  api<LeadConsent & { applied: Record<string, string> }>(
    `/leads/${leadId}/consent/withdraw`,
    { method: "POST", body: { source, detail } });
