import { api } from "./client";
import type { LeadOut, LeadStatus } from "./types";

export function listLeads(
  strategyId: string,
  params: { status?: LeadStatus; page?: number } = {},
): Promise<{ items: LeadOut[]; total: number; limit: number; offset: number }> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.page) q.set("page", String(params.page));
  const qs = q.toString();
  return api(`/strategies/${strategyId}/leads${qs ? `?${qs}` : ""}`);
}

export function getLead(id: string): Promise<LeadOut> {
  return api(`/leads/${id}`);
}

export function updateLeadStatus(
  id: string,
  status: LeadStatus,
): Promise<LeadOut> {
  return api(`/leads/${id}`, { method: "PATCH", body: { status } });
}

export function deleteLead(id: string): Promise<void> {
  return api(`/leads/${id}`, { method: "DELETE" });
}

export function getOptin(
  leadId: string,
): Promise<{ current_status: string; history: unknown[] }> {
  return api(`/leads/${leadId}/whatsapp-optin`);
}

/** Allowed drag transitions on the kanban. The backend re-validates -
 *  this map only decides what the UI OFFERS (disallowed moves snap back). */
export const ALLOWED_TRANSITIONS: Record<LeadStatus, LeadStatus[]> = {
  sourced: ["dropped"],
  enriched: ["dropped"],
  email_found: ["dropped"],
  verified: ["flagged", "dropped"],
  flagged: ["verified", "dropped"],
  dropped: [],
  contacted: ["replied"],
  replied: ["meeting_booked"],
  // Feature Group 7 — mirrors app/api/ui_support.py. "Log Meeting Outcome"
  // is the normal way into these; a drag only moves the status.
  meeting_booked: ["opportunity", "disqualified"],
  opportunity: ["closed_won", "closed_lost", "disqualified"],
  closed_won: [],
  closed_lost: ["opportunity"],
  disqualified: [],
};

export function canTransition(from: LeadStatus, to: LeadStatus): boolean {
  return from === to || (ALLOWED_TRANSITIONS[from] ?? []).includes(to);
}