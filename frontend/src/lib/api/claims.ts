import { api } from "./client";
import type { ClaimCheck } from "../claims";

export interface ClaimSummary {
  days: number;
  totals: { verified: number; stripped: number; rewritten: number };
  by_category: Record<string, Partial<Record<"verified" | "stripped" | "rewritten", number>>>;
}

export const getLeadClaimChecks = (leadId: string) =>
  api<ClaimCheck[]>(`/leads/${leadId}/claim-checks`);

export const getClaimSummary = (days = 30) =>
  api<ClaimSummary>(`/claim-checks/summary?days=${days}`);
