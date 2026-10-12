/** Voice twin (docs/features/voice-twin.md). NOTE: `body` is passed as an
 *  OBJECT -- api() stringifies it itself. Recordings go as a RAW body. */

import { api } from "./client";
import type {
  LiveCalls,
  SettingsForm,
  VerificationChallenge,
  VoiceTwinSettings,
  VoiceTwinState,
} from "../voiceTwin";
import { baseType, consentBody } from "../voiceTwin";

export const getVoiceClone = () => api<VoiceTwinState>("/me/voice-clone");

export const signVoiceConsent = (signature: string, ownVoice: boolean, version: string,
                                 template: string) =>
  api<VoiceTwinState>("/me/voice-clone/consent", {
    method: "POST", body: consentBody(signature, ownVoice, version, template),
  });

export const uploadVoiceSample = (file: Blob, filename: string) =>
  api<VoiceTwinState>("/me/voice-clone/samples", {
    method: "POST", raw: { body: file, contentType: baseType(file.type), filename },
  });

export const submitVoiceSamples = () =>
  api<VoiceTwinState>("/me/voice-clone/submit", { method: "POST" });

export const getVoiceVerification = () =>
  api<VerificationChallenge>("/me/voice-clone/verification");

export const sendVoiceVerification = (recording: Blob) =>
  api<VoiceTwinState>("/me/voice-clone/verification", {
    method: "POST", raw: { body: recording, contentType: baseType(recording.type) },
  });

export const refreshVoiceClone = () =>
  api<VoiceTwinState>("/me/voice-clone/refresh", { method: "POST" });

export const previewVoiceClone = () => api<Blob>("/me/voice-clone/preview", { blob: true });

export const setUseMyVoice = (enabled: boolean) =>
  api<VoiceTwinState>("/me/voice-clone/use", { method: "PUT", body: { enabled } });

export const revokeVoiceClone = () =>
  api<VoiceTwinState>("/me/voice-clone", { method: "DELETE" });

export const getVoiceTwinSettings = () => api<VoiceTwinSettings>("/voice-twin/settings");

export const saveVoiceTwinSettings = (changes: Partial<SettingsForm>) =>
  api<VoiceTwinSettings>("/voice-twin/settings", { method: "PUT", body: changes });

export const resumeAiCalls = () =>
  api<VoiceTwinSettings>("/voice-twin/resume", { method: "POST", body: { acknowledge: true } });

export const getLiveCalls = () => api<LiveCalls>("/voice-twin/live-calls");

export const takeOverCall = (callId: string) =>
  api<{ transferred: boolean; to: string }>(`/calls/${callId}/takeover`, { method: "POST" });
