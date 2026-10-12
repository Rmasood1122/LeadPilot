/**
 * Voice twin -- "Your voice on calls" (docs/features/voice-twin.md).
 *
 * Pure logic for Settings > Voice and the live-call banner: which step the
 * clone is at, what each provider status honestly means, request bodies, and
 * client-side checks that mirror the server's (the server is the authority;
 * these only save a round trip).
 *
 * Never built here, on purpose: anything that hides that the caller is an AI.
 * Every call opens with "Hi, this is <you>'s AI assistant, using <you>'s
 * voice. This call is recorded." -- the server enforces it.
 */

export type VoiceCloneStatus =
  | "consented"
  | "collecting"
  | "verifying"
  | "training"
  | "ready"
  | "failed"
  | "revoke_pending"
  | "revoked";

export interface VoiceClone {
  id: string;
  status: VoiceCloneStatus;
  provider: string;
  consent_version: string;
  consent_text: string;
  consent_signature: string;
  consented_at: string | null;
  sample_count: number;
  sample_bytes: number;
  provider_state: Record<string, unknown> | null;
  error: string | null;
  ready_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
}

export interface VoiceTwinSettings {
  use_clone_for_calls: boolean;
  answer_inbound: boolean;
  inbound_number_linked: boolean;
  /** This account has a phone number of its own to answer on. */
  own_number_configured?: boolean;
  /** Masked for workspace members; only the owner may change it. */
  transfer_number: string | null;
  can_edit_transfer_number?: boolean;
  assistant_notes: string | null;
  paused: boolean;
  paused_at: string | null;
  paused_reason: string | null;
  feature_enabled?: boolean;
}

export interface VoiceTwinLimits {
  max_samples: number;
  max_sample_bytes: number;
  max_total_bytes: number;
  types: string[];
}

export interface VoiceTwinState {
  feature_enabled: boolean;
  /** `template` has a {name} placeholder: the page shows it with the
   *  signature being typed, and sends exactly that text back. */
  consent: { version: string; template: string; text: string };
  limits: VoiceTwinLimits;
  clone: VoiceClone | null;
  settings: VoiceTwinSettings;
  opening_line: string;
  verify_on_elevenlabs: string;
}

export interface VerificationChallenge {
  kind: "image" | "text" | "unavailable";
  image?: string;
  text?: string;
  fallback: string;
}

export interface LiveCall {
  id: string;
  direction: "inbound" | "outbound";
  status: string;
  voice_clone_used: boolean;
  lead_id: string | null;
  who: string;
  started_at: string | null;
  can_take_over: boolean;
}

export type CloneStep =
  | "disabled"
  | "consent"
  | "upload"
  | "verify"
  | "training"
  | "ready"
  | "failed"
  | "revoking";

/** Where the person is in the flow. A revoked clone means "start again"
 *  (consent), except while the provider delete is still pending. */
export function cloneStep(state: Pick<VoiceTwinState, "feature_enabled" | "clone">): CloneStep {
  const status = state.clone?.status;
  if (status === "revoke_pending") return "revoking";
  if (!state.feature_enabled && status !== "ready") return "disabled";
  if (!status || status === "revoked") return "consent";
  if (status === "consented" || status === "collecting") return "upload";
  if (status === "verifying") return "verify";
  if (status === "training") return "training";
  if (status === "ready") return "ready";
  return "failed";
}

/** The provider's status, said plainly -- never "ready" before it is. */
export function statusLabel(status: VoiceCloneStatus | undefined | null): string {
  switch (status) {
    case "consented":
      return "Consent signed — add recordings";
    case "collecting":
      return "Recordings uploaded to ElevenLabs";
    case "verifying":
      return "Waiting for your voice verification at ElevenLabs";
    case "training":
      return "ElevenLabs is training your voice (this can take hours)";
    case "ready":
      return "Ready";
    case "failed":
      return "ElevenLabs could not create the voice";
    case "revoke_pending":
      return "Revoked — deleting at ElevenLabs (retrying)";
    case "revoked":
      return "Revoked and deleted";
    default:
      return "Not set up";
  }
}

export function consentError(signature: string, ownVoice: boolean): string | null {
  if (!ownVoice) return 'Tick "This is my own voice" — you can only clone your own voice.';
  if (signature.trim().length < 2) return "Type your full name to sign.";
  return null;
}

export function normaliseSignature(signature: string): string {
  return signature.trim().replace(/\s+/g, " ").slice(0, 200);
}

/** The exact consent text shown, with the typed signature in it -- the text
 *  the server stores (and refuses if it differs). */
export function consentTextFor(template: string, signature: string): string {
  const name = normaliseSignature(signature) || "<your name>";
  return template.split("{name}").join(name);
}

export function consentBody(signature: string, ownVoice: boolean, version: string, template: string) {
  return {
    signature: normaliseSignature(signature),
    own_voice: ownVoice,
    consent_version: version,
    consent_text: consentTextFor(template, signature),
  };
}

/** The base MIME type (no codecs) the server accepts, or null. */
export function baseType(type: string): string {
  return (type || "").split(";")[0].trim().toLowerCase();
}

export function sampleError(
  file: { size: number; type: string },
  limits: VoiceTwinLimits,
  used: { count: number; bytes: number },
): string | null {
  if (!limits.types.includes(baseType(file.type))) {
    return "Upload audio only: MP3, WAV, M4A, WEBM, OGG or FLAC.";
  }
  if (file.size > limits.max_sample_bytes) {
    return `Each recording can be at most ${Math.floor(limits.max_sample_bytes / (1024 * 1024))} MB.`;
  }
  if (used.count >= limits.max_samples) return `At most ${limits.max_samples} recordings.`;
  if (used.bytes + file.size > limits.max_total_bytes) {
    return `All recordings together can be at most ${Math.floor(limits.max_total_bytes / (1024 * 1024))} MB.`;
  }
  return null;
}

/** In-browser recording needs MediaRecorder and getUserMedia; otherwise the
 *  page offers file upload only. */
export function canRecord(env: {
  MediaRecorder?: unknown;
  navigator?: { mediaDevices?: { getUserMedia?: unknown } };
}): boolean {
  return typeof env.MediaRecorder === "function"
    && typeof env.navigator?.mediaDevices?.getUserMedia === "function";
}

/** The first recorder format this browser supports that the server accepts. */
export function pickRecorderType(isTypeSupported: (t: string) => boolean): string | null {
  for (const t of ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"]) {
    if (isTypeSupported(t)) return t;
  }
  return null;
}

export function extensionFor(type: string): string {
  const base = baseType(type);
  return ({ "audio/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a", "audio/mpeg": "mp3",
            "audio/wav": "wav" } as Record<string, string>)[base] ?? "audio";
}

export interface SettingsForm {
  answer_inbound: boolean;
  transfer_number: string;
  assistant_notes: string;
}

/** Only the fields that changed -- the server audits each change. */
export function settingsBody(form: SettingsForm, initial: VoiceTwinSettings): Partial<SettingsForm> {
  const out: Partial<SettingsForm> = {};
  if (form.answer_inbound !== initial.answer_inbound) out.answer_inbound = form.answer_inbound;
  if (form.transfer_number.trim() !== (initial.transfer_number ?? "")) {
    out.transfer_number = form.transfer_number.trim();
  }
  if (form.assistant_notes.trim() !== (initial.assistant_notes ?? "")) {
    out.assistant_notes = form.assistant_notes.trim();
  }
  return out;
}

export interface LiveCalls {
  calling_enabled: boolean;
  calls: LiveCall[];
}

/** Poll every 15 s while a call is live, every 60 s otherwise, never while
 *  AI calling is switched off (L7). */
export function liveCallsPollMs(data: LiveCalls | undefined | null): number | false {
  if (!data) return 60_000;
  if (!data.calling_enabled) return false;
  return data.calls.length ? 15_000 : 60_000;
}

export function showLiveBanner(calls: LiveCall[] | undefined | null): boolean {
  return Array.isArray(calls) && calls.some((c) => c.status === "in_progress" || c.status === "ringing");
}

export function liveCallText(call: LiveCall): string {
  const voice = call.voice_clone_used ? " in your voice" : "";
  return call.direction === "inbound"
    ? `Your AI assistant is answering ${call.who}${voice}.`
    : `Your AI assistant is calling ${call.who}${voice}.`;
}

export const REVOKE_CONFIRM =
  "Revoke your voice clone? It stops being used immediately and is deleted at ElevenLabs. "
  + "To use your voice again you would sign the consent and upload recordings again.";
