import { api } from "./client";

export interface InterviewStatus {
  due: boolean;
  questions: string[];
  open_interview_id: string | null;
  has_style_profile: boolean;
}

export interface StyleProfile {
  tone: string;
  formality: number;
  vocabulary_level: string;
  sentence_length: string;
  avg_words_per_sentence: number | null;
  humor: string;
  greeting_style: string;
  signoff_style: string;
  signature_habits: string[];
  do: string[];
  dont: string[];
  summary: string;
}

export interface Interview {
  id: string;
  mode: "text" | "voice";
  status: "in_progress" | "proposed" | "applied" | "discarded" | "snoozed";
  answers: { index: number; text: string }[];
  proposed_profile: StyleProfile | null;
  recommendations: string[];
  next_due_at: string | null;
}

export const getInterviewStatus = () => api<InterviewStatus>("/interview/status");
export const startInterview = (mode: "text" | "voice", voiceNoticeAck: boolean) =>
  api<Interview>("/interview/start", { body: { mode, voice_notice_ack: voiceNoticeAck } });
export const getInterview = (id: string) => api<Interview>(`/interview/${id}`);
export const saveAnswers = (id: string, answers: { index: number; text: string }[]) =>
  api<Interview>(`/interview/${id}/answers`, { method: "PUT", body: { answers } });
export const finishInterview = (id: string) =>
  api<Interview>(`/interview/${id}/finish`, { body: {} });
export const applyInterview = (id: string, profile?: StyleProfile) =>
  api<Interview>(`/interview/${id}/apply`, { body: profile ? { profile } : {} });
export const discardInterview = (id: string) =>
  api<Interview>(`/interview/${id}/discard`, { body: {} });
export const snoozeInterview = (days: number) =>
  api<Interview>("/interview/snooze", { body: { days } });
