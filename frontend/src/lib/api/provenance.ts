import { api } from "./client";
import type { LeadProvenance } from "../provenance";

/** Part 1 Feature 10 — where each enriched field came from. */

export const getLeadProvenance = (leadId: string) =>
  api<LeadProvenance>(`/leads/${leadId}/provenance`);
