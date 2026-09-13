import { api } from "./client";
import type { ConversionResponse } from "../conversionProbability";

export const getLeadConversion = (leadId: string) =>
  api<ConversionResponse>(`/leads/${leadId}/conversion`);

export const reactivateLead = (leadId: string) =>
  api<{ engagement_state: string; resumed_enrollments: number }>(
    `/leads/${leadId}/conversion/reactivate`, { method: "POST" });
