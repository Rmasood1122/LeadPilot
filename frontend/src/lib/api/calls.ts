/** Feature Group 6 — AI phone calls. */

import { api } from "./client";

export type CallOutcome =
  | "voicemail_dropped"
  | "voicemail"
  | "no_answer"
  | "answered"
  | "interested"
  | "not_interested"
  | "failed";

export interface CallAnalysis {
  outcome: string;
  summary: string;
  objections: string[];
  interest_signals: string[];
  next_step: string;
  sentiment: string;
  stop_request: boolean;
}

export interface CallSummary {
  id: string;
  lead_id: string;
  provider: string;
  to_number: string;
  status: string;
  outcome: CallOutcome | null;
  duration_seconds: number | null;
  recording_url: string | null;
  voicemail_audio_url: string | null;
  ended_reason: string | null;
  analysis_json: CallAnalysis | null;
  error: string | null;
  created_at: string;
  ended_at: string | null;
  lead_name?: string | null;
}

export interface CallDetail extends CallSummary {
  script_json: {
    first_message: string;
    objective: string;
    talking_points: string[];
    objection_handling: { objection: string; response: string }[];
    questions: string[];
    close: string;
    voicemail: string;
  } | null;
  voicemail_text: string | null;
  transcript: string | null;
}

export function listStrategyCalls(strategyId: string): Promise<CallSummary[]> {
  return api(`/strategies/${strategyId}/calls`);
}

export function listLeadCalls(leadId: string): Promise<CallDetail[]> {
  return api(`/leads/${leadId}/calls`);
}

export function getCall(callId: string): Promise<CallDetail> {
  return api(`/calls/${callId}`);
}

export function callNow(leadId: string, brief?: string): Promise<CallDetail> {
  return api(`/leads/${leadId}/call`, { method: "POST", body: brief ? { brief } : {} });
}

export function recordPhoneConsent(leadId: string, source: string) {
  return api(`/leads/${leadId}/phone-consent`, { method: "PUT", body: { source } });
}

export function revokePhoneConsent(leadId: string): Promise<void> {
  return api(`/leads/${leadId}/phone-consent`, { method: "DELETE" });
}

export const OUTCOME_LABEL: Record<CallOutcome, string> = {
  voicemail_dropped: "Voicemail left",
  voicemail: "Voicemail",
  no_answer: "No answer",
  answered: "Answered",
  interested: "Interested",
  not_interested: "Not interested",
  failed: "Failed",
};

export function outcomeTone(outcome: CallOutcome | null):
  "success" | "destructive" | "warning" | "accent" | "default" {
  if (outcome === "interested") return "success";
  if (outcome === "not_interested" || outcome === "failed") return "destructive";
  if (outcome === "answered") return "accent";
  if (outcome === "voicemail_dropped" || outcome === "voicemail") return "warning";
  return "default";
}

/** 185 -> "3:05"; null -> "—". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds < 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
