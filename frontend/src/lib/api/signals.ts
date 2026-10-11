import { api } from "./client";
import type { LeadSignals } from "../signals";

/** F02 Signal Radar — dated "why now" signals with source links. */

export const getLeadSignals = (leadId: string) =>
  api<LeadSignals>(`/leads/${leadId}/signals`);

/** Re-derives from data already stored on the lead. Never calls a vendor. */
export const refreshLeadSignals = (leadId: string) =>
  api<LeadSignals>(`/leads/${leadId}/signals/refresh`, { method: "POST" });
