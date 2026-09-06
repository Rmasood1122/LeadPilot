/** Engagement Hub, Feature 3 — meetings domain module. */

import { api } from "./client";

export type MeetingPlatform = "google_meet" | "zoom" | "teams" | "custom";
export type MeetingStatus =
  | "scheduled"
  | "in_progress"
  | "completed"
  | "cancelled";

export interface ActionItem {
  text: string;
  owner: "us" | "client";
  due: string | null;
  done: boolean;
}

export interface MeetingParticipant {
  id: string;
  name: string | null;
  email: string | null;
  role: "host" | "client" | "observer";
  joined_at: string | null;
  left_at: string | null;
}

export interface Meeting {
  id: string;
  booking_id: string | null;
  lead_id: string | null;
  platform: MeetingPlatform;
  title: string | null;
  meeting_url: string | null;
  start_at: string;
  end_at: string;
  actual_start_at: string | null;
  actual_end_at: string | null;
  status: MeetingStatus;
  summary: string | null;
  sentiment: string | null;
  action_items: ActionItem[] | null;
  key_points: string[] | null;
  next_steps: string[] | null;
  recording_url: string | null;
}

export interface MeetingDetail extends Meeting {
  raw_notes: string | null;
  ai_notes: string | null;
  transcript: string | null;
  participants: MeetingParticipant[];
}

/** `platform_error` is set when a platform integration was asked for and
 *  declined (scope not granted, Zoom not configured, provider down). The
 *  meeting is still created — see the backend module docstring for why that
 *  is a field on a 201 rather than a failed request. */
export interface MeetingCreateResult extends MeetingDetail {
  platform_error: string | null;
}

export function createMeeting(body: {
  booking_id?: string | null;
  lead_id?: string | null;
  platform: MeetingPlatform;
  title?: string | null;
  meeting_url?: string | null;
  start_at?: string | null;
  end_at?: string | null;
}): Promise<MeetingCreateResult> {
  return api("/meetings", { method: "POST", body });
}

export function listMeetings(params: {
  upcoming?: boolean;
  status?: MeetingStatus;
  leadId?: string;
  limit?: number;
} = {}): Promise<Meeting[]> {
  const q = new URLSearchParams();
  if (params.upcoming !== undefined) q.set("upcoming", String(params.upcoming));
  if (params.status) q.set("status", params.status);
  if (params.leadId) q.set("lead_id", params.leadId);
  if (params.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return api(`/meetings${qs ? `?${qs}` : ""}`);
}

export function getMeeting(id: string): Promise<MeetingDetail> {
  return api(`/meetings/${id}`);
}

export function startMeeting(id: string): Promise<MeetingDetail> {
  return api(`/meetings/${id}/start`, { method: "POST" });
}

/** Full replace, not append — the client owns a textarea and sends its
 *  contents. See the backend handler. */
export function saveNotes(
  id: string,
  rawNotes: string,
): Promise<MeetingDetail> {
  return api(`/meetings/${id}/notes`, {
    method: "PUT",
    body: { raw_notes: rawNotes },
  });
}

export function endMeeting(
  id: string,
  generateSummary = true,
): Promise<MeetingDetail> {
  return api(`/meetings/${id}/end?generate_summary=${generateSummary}`, {
    method: "POST",
  });
}

export function generateSummary(id: string): Promise<MeetingDetail> {
  return api(`/meetings/${id}/generate-summary`, { method: "POST" });
}

export function getActionItems(
  id: string,
): Promise<{ meeting_id: string; items: ActionItem[]; open_count: number }> {
  return api(`/meetings/${id}/action-items`);
}

export function saveActionItems(
  id: string,
  items: ActionItem[],
): Promise<{ meeting_id: string; items: ActionItem[] }> {
  return api(`/meetings/${id}/action-items`, {
    method: "PUT",
    body: { action_items: items },
  });
}
