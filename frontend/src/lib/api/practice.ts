import { api } from "./client";
import type {
  CallScript,
  Difficulty,
  PracticeHistory,
  Readiness,
  RoleplaySession,
  ScriptResponse,
} from "../practice";

/** Part 2 — the call script, the readiness checklist and roleplay practice.
 *
 *  Every write passes `body` as an OBJECT: api() stringifies it itself, and
 *  JSON.stringify here would send a JSON string and get a 422. See the note at
 *  the bottom of ./client.ts. */

export const getScript = (briefId: string) =>
  api<ScriptResponse>(`/meeting-prep/${briefId}/script`);

export const saveScript = (briefId: string, script: CallScript) =>
  api<ScriptResponse>(`/meeting-prep/${briefId}/script`,
                      { method: "PUT", body: script });

export const getReadiness = (briefId: string) =>
  api<Readiness>(`/meeting-prep/${briefId}/readiness`);

export const setPracticeRequired = (briefId: string, required: boolean) =>
  api<Readiness>(`/meeting-prep/${briefId}/practice-required`,
                 { method: "POST", body: { required } });

export const startPractice = (
  opts: { lead_id?: string; brief_id?: string; difficulty?: Difficulty } = {},
) => api<RoleplaySession>("/practice/sessions", { method: "POST", body: opts });

export const getPracticeSession = (id: string) =>
  api<RoleplaySession>(`/practice/sessions/${id}`);

export interface ReplyResult {
  status: "ok" | "failed" | "closed" | "limit";
  prospect: string | null;
  turn_count: number;
  limit_reached: boolean;
  session: RoleplaySession;
}

export const sendPracticeReply = (id: string, message: string) =>
  api<ReplyResult>(`/practice/sessions/${id}/reply`,
                   { method: "POST", body: { message } });

export const finishPractice = (id: string, abandoned = false) =>
  api<RoleplaySession>(`/practice/sessions/${id}/finish`,
                       { method: "POST", body: { abandoned } });

export const getPracticeHistory = (leadId?: string) =>
  api<PracticeHistory>(`/practice/sessions${leadId ? `?lead_id=${leadId}` : ""}`);
