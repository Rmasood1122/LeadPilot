/** Feature Group 5 — connected LinkedIn accounts and per-lead LinkedIn state. */

import { api } from "./client";

export interface LinkedInUsage {
  connect: number;
  message: number;
  inmail: number;
}

export interface LinkedInAccount {
  id: string;
  unipile_account_id: string;
  display_name: string | null;
  profile_url: string | null;
  has_premium: boolean;
  inmail_credits: number | null;
  inmail_sent_total: number;
  is_active: boolean;
  status: string;
  last_used_at: string | null;
  usage_today: LinkedInUsage;
  limits: { connect: number; message: number };
}

export interface LeadLinkedInState {
  linkedin_url: string | null;
  provider_id: string | null;
  is_premium: boolean | null;
  connection_status: "pending" | "connected" | null;
  invited_at: string | null;
  connected_at: string | null;
  account_id: string | null;
  has_conversation: boolean;
}

export function listLinkedInAccounts(): Promise<LinkedInAccount[]> {
  return api("/integrations/linkedin/accounts");
}

/** Unipile's hosted page — the user signs in to LinkedIn there, never here. */
export function linkedInConnectUrl(): Promise<{ url: string }> {
  return api("/integrations/linkedin/connect", { method: "POST" });
}

export function linkLinkedInAccount(unipileAccountId: string): Promise<LinkedInAccount> {
  return api("/integrations/linkedin/accounts", {
    method: "POST",
    body: { unipile_account_id: unipileAccountId },
  });
}

export function setLinkedInAccountActive(id: string, isActive: boolean): Promise<LinkedInAccount> {
  return api(`/integrations/linkedin/accounts/${id}`, {
    method: "PATCH",
    body: { is_active: isActive },
  });
}

export function refreshLinkedInAccount(id: string): Promise<LinkedInAccount> {
  return api(`/integrations/linkedin/accounts/${id}/refresh`, { method: "POST" });
}

export function deleteLinkedInAccount(id: string): Promise<void> {
  return api(`/integrations/linkedin/accounts/${id}`, { method: "DELETE" });
}

export function getLeadLinkedIn(leadId: string): Promise<LeadLinkedInState> {
  return api(`/leads/${leadId}/linkedin`);
}

/** Fraction of today's ceiling used, 0..1, for a usage bar. */
export function usageFraction(used: number, limit: number): number {
  if (limit <= 0) return 1;
  return Math.max(0, Math.min(1, used / limit));
}
