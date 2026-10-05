/** Pure rules for the monthly style interview. The server re-checks all of it. */
import { ApiError } from "@/lib/api/client";
import type { StyleProfile } from "@/lib/api/interview";

export const MIN_ANSWER_CHARS = 40;
export const MIN_USABLE_ANSWERS = 3;
export const MAX_ANSWER_CHARS = 4000;
export const SNOOZE_DAYS = 7;

export const usableAnswers = (answers: string[]): number =>
  answers.filter((a) => a.trim().length >= MIN_ANSWER_CHARS).length;
export const canFinish = (answers: string[]): boolean => usableAnswers(answers) >= MIN_USABLE_ANSWERS;

/** Browser speech recognition, if there is one. Audio goes to the BROWSER's
 *  speech service, never to LeadPilot; we only ever receive the text. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function speechCtor(w: any): (new () => any) | null {
  return (w && (w.SpeechRecognition || w.webkitSpeechRecognition)) || null;
}
export const speechSupported = (w: unknown): boolean => speechCtor(w) !== null;

export function appendTranscript(existing: string, chunk: string): string {
  const c = chunk.trim();
  if (!c) return existing;
  const base = existing.replace(/\s+$/, "");
  return (base ? base + " " : "") + c;
}

export const VOICE_NOTICE =
  "When you dictate, your browser sends your voice to its own speech service (for example Google in Chrome, " +
  "Apple in Safari) to turn it into text. LeadPilot receives and stores only the text. No audio is recorded or kept by LeadPilot.";

export function interviewErrorMessage(err: unknown): string {
  if (err instanceof ApiError && [409, 422, 429, 502].includes(err.status)) {
    return err.status === 429 ? "Too many requests. Wait a minute and try again." : err.message;
  }
  return "Something went wrong. Try again.";
}

/** The editable form of a proposed profile (lists become one item per line). */
export interface ProfileForm {
  tone: string; formality: number; greeting_style: string; signoff_style: string;
  do: string; dont: string; summary: string;
}
export const profileToForm = (p: StyleProfile): ProfileForm => ({
  tone: p.tone, formality: p.formality, greeting_style: p.greeting_style,
  signoff_style: p.signoff_style, do: p.do.join("\n"), dont: p.dont.join("\n"), summary: p.summary,
});
const lines = (s: string): string[] => s.split("\n").map((x) => x.trim()).filter(Boolean).slice(0, 6);
/** Edited fields laid over the proposal; everything not editable stays as proposed. */
export function formToProfile(base: StyleProfile, f: ProfileForm): StyleProfile {
  const formality = Math.min(5, Math.max(1, Math.round(Number(f.formality)) || base.formality));
  return { ...base, tone: f.tone.trim(), formality, greeting_style: f.greeting_style.trim(),
           signoff_style: f.signoff_style.trim(), do: lines(f.do), dont: lines(f.dont),
           summary: f.summary.trim() };
}

export const FORMALITY_LABEL: Record<number, string> = {
  1: "very casual", 2: "casual", 3: "neutral", 4: "formal", 5: "very formal",
};
