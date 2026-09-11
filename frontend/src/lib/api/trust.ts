/** Feature Group 9 — deliverability health and the compliance audit log. */

import { api } from "./client";

export interface DomainHealth {
  domain: string;
  address: string;
  health: {
    score: number;
    source: string;
    checked_at: string;
    details: {
      spf: boolean;
      dmarc: boolean;
      dmarc_policy: string | null;
      dkim: boolean;
      bounce_rate: number | null;
      reasons: string[];
    };
  } | null;
  blacklist: { listed_on: string[]; unknown: string[]; source: string; checked_at: string } | null;
  history: { checked_at: string; score: number }[];
}

export interface DeliverabilityStatus {
  threshold: number;
  monitoring_enabled: boolean;
  domains: DomainHealth[];
}

export interface AuditRow {
  id: string;
  lead_id: string | null;
  message_id: string | null;
  channel: string;
  region: string | null;
  regime: string | null;
  decision: string;
  checks: Record<string, unknown> | null;
  ts: string | null;
}

export const getDeliverability = (): Promise<DeliverabilityStatus> => api("/deliverability");
export const runDeliverabilityCheck = (): Promise<DeliverabilityStatus> =>
  api("/deliverability/check", { method: "POST" });
export const listComplianceAudit = (limit = 50): Promise<AuditRow[]> =>
  api(`/compliance/audit?limit=${limit}`);

/** Score -> tone, with the threshold the admin configured. */
export function healthTone(score: number | null | undefined, threshold: number):
  "positive" | "warning" | "danger" | "default" {
  if (score === null || score === undefined) return "default";
  if (score >= threshold) return "positive";
  return score < 40 ? "danger" : "warning";
}

export const DECISION_LABELS: Record<string, string> = {
  sent: "Sent",
  blocked_suppressed: "Blocked — suppressed",
  blocked_no_address: "Blocked — no address",
  skipped_no_consent: "Skipped — no consent",
};
