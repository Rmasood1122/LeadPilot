/** Feature Group 7 — meeting prep briefs, meeting outcomes, follow-up drafts. */

import { api } from "./client";

export type MeetingPrepStatus = "pending" | "generating" | "ready" | "failed";

export interface PrepObjection {
  objection: string;
  response: string;
}

/** Mirrors app/services/meeting_prep.py::clean_sections — always every key. */
export interface PrepSections {
  company_overview: string;
  recent_activity: string;
  why_they_booked: string;
  pain_points: string[];
  likely_objections: PrepObjection[];
  talking_points: string[];
  discovery_questions: string[];
  competitive_landscape: string;
  next_steps: string[];
  deal_structure: string;
  opening_60_seconds: string;
}

/** Copied from the records server-side, never model-written. */
export interface PrepProfile {
  name: string | null;
  title: string | null;
  company: string | null;
  email: string | null;
  phone: string | null;
  linkedin_url: string | null;
  location: string | null;
  industry: string | null;
  company_size: number | string | null;
  company_website: string | null;
  founded_year: number | string | null;
  funding: string | null;
  status: string | null;
  linkedin_posts?: { text: string; posted_at: string | null; url: string | null }[];
  company_news?: {
    headline: string | null;
    summary: string | null;
    published_at: string | null;
    url: string | null;
  }[];
}

export interface MeetingPrepBrief {
  id: string;
  lead_id: string;
  source: "calendly" | "leadpilot_calendar" | "manual" | string;
  status: MeetingPrepStatus;
  meeting_start_at: string | null;
  meeting_url: string | null;
  content_md: string | null;
  sections_json: PrepSections | null;
  profile_json: PrepProfile | null;
  opening_script: string | null;
  error: string | null;
  generated_at: string | null;
  reminder_24h_sent_at: string | null;
  reminder_1h_sent_at: string | null;
  cancelled_at: string | null;
  created_at: string;
}

export interface MeetingPrepSummary {
  id: string;
  source: string;
  status: MeetingPrepStatus;
  meeting_start_at: string | null;
  cancelled_at: string | null;
  created_at: string;
}

export interface LeadPrep {
  brief: MeetingPrepBrief | null;
  history: MeetingPrepSummary[];
}

export function getLeadPrep(leadId: string): Promise<LeadPrep> {
  return api(`/leads/${leadId}/meeting-prep`);
}

export function requestLeadPrep(
  leadId: string,
  meetingId?: string | null,
): Promise<MeetingPrepBrief> {
  return api(`/leads/${leadId}/meeting-prep`, {
    method: "POST",
    body: { meeting_id: meetingId ?? null },
  });
}

export function regeneratePrep(briefId: string): Promise<MeetingPrepBrief> {
  return api(`/meeting-prep/${briefId}/regenerate`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Meeting outcomes
// ---------------------------------------------------------------------------

export type MeetingOutcomeKind =
  | "interested"
  | "needs_follow_up"
  | "not_a_fit"
  | "closed_won"
  | "closed_lost";

export type DraftStatus =
  | "pending"
  | "draft_saved"
  | "sent"
  | "not_connected"
  | "reauth_required"
  | "suppressed"
  | "no_address"
  | "generation_failed"
  | "failed";

export interface MeetingOutcome {
  id: string;
  lead_id: string;
  meeting_id: string | null;
  deal_id: string | null;
  outcome: MeetingOutcomeKind;
  notes: string | null;
  previous_status: string | null;
  new_status: string | null;
  followup_subject: string | null;
  followup_body: string | null;
  draft_status: DraftStatus;
  draft_error: string | null;
  gmail_draft_id: string | null;
  sent_at: string | null;
  created_at: string;
  gmail_drafts_url: string;
}

export interface LogOutcomeBody {
  outcome: MeetingOutcomeKind;
  notes?: string | null;
  meeting_id?: string | null;
  deal_value?: number | null;
  currency?: string;
  deal_name?: string | null;
  generate_followup?: boolean;
}

export function logMeetingOutcome(
  leadId: string,
  body: LogOutcomeBody,
): Promise<MeetingOutcome> {
  return api(`/leads/${leadId}/meeting-outcome`, { method: "POST", body });
}

export function listMeetingOutcomes(leadId: string): Promise<MeetingOutcome[]> {
  return api(`/leads/${leadId}/meeting-outcomes`);
}

export function editFollowupDraft(
  outcomeId: string,
  subject: string,
  body: string,
): Promise<MeetingOutcome> {
  return api(`/meeting-outcomes/${outcomeId}/draft`, {
    method: "PUT",
    body: { subject, body },
  });
}

export function regenerateFollowupDraft(outcomeId: string): Promise<MeetingOutcome> {
  return api(`/meeting-outcomes/${outcomeId}/draft/regenerate`, { method: "POST" });
}

export function sendFollowup(outcomeId: string): Promise<MeetingOutcome> {
  return api(`/meeting-outcomes/${outcomeId}/send`, { method: "POST" });
}
