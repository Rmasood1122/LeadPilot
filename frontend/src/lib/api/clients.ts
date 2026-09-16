import { api } from "./client";
import type {
  ClientBilling,
  ClientOverview,
  ClientReport,
  ClientWorkspace,
} from "../clients";

/** Part 1 Feature 11 — per-client agency workspaces.
 *
 *  Every call is scoped to the active team workspace by the X-Workspace-Id
 *  header the shared api() client already sends. */

export const listClients = (includeArchived = false) =>
  api<ClientOverview & { archived?: ClientWorkspace[] }>(
    `/clients?include_archived=${includeArchived}`);

export const getClient = (id: string) =>
  api<ClientWorkspace & ClientReport>(`/clients/${id}`);

export interface ClientDraft {
  name: string;
  contact_name?: string;
  contact_email?: string;
  billing_email?: string;
  billing_reference?: string;
  monthly_fee_cents?: number;
  per_meeting_fee_cents?: number;
  currency?: string;
  notes?: string;
}

/** `body` is an OBJECT — api() stringifies it itself. */
export const createClient = (draft: ClientDraft) =>
  api<ClientWorkspace>("/clients", { method: "POST", body: draft });

export const updateClient = (id: string,
                             patch: Partial<ClientDraft & { status: string }>) =>
  api<ClientWorkspace>(`/clients/${id}`, { method: "PATCH", body: patch });

export const getClientReport = (id: string) =>
  api<ClientReport>(`/clients/${id}/report`);

export const getClientBilling = (id: string) =>
  api<ClientBilling>(`/clients/${id}/billing`);

export const addClientDomain = (id: string, domain: string, note?: string) =>
  api<ClientWorkspace>(`/clients/${id}/domains`,
                       { method: "POST", body: { domain, note } });

export const removeClientDomain = (id: string, domain: string) =>
  api<ClientWorkspace>(`/clients/${id}/domains/${encodeURIComponent(domain)}`,
                       { method: "DELETE" });

export const assignStrategyToClient = (strategyId: string, clientId: string | null) =>
  api<{ strategy_id: string; client_id: string | null; client_name: string | null }>(
    `/strategies/${strategyId}/client`,
    { method: "POST", body: { client_id: clientId } });
