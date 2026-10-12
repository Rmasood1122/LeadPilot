import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getLiveCalls,
  revokeVoiceClone,
  saveVoiceTwinSettings,
  setUseMyVoice,
  signVoiceConsent,
  takeOverCall,
  uploadVoiceSample,
} from "@/lib/api/voiceTwin";
import {
  baseType,
  canRecord,
  cloneStep,
  consentBody,
  consentError,
  consentTextFor,
  liveCallsPollMs,
  extensionFor,
  liveCallText,
  pickRecorderType,
  sampleError,
  settingsBody,
  showLiveBanner,
  statusLabel,
  type LiveCall,
  type VoiceClone,
  type VoiceTwinSettings,
} from "@/lib/voiceTwin";

const LIMITS = {
  max_samples: 25,
  max_sample_bytes: 25 * 1024 * 1024,
  max_total_bytes: 250 * 1024 * 1024,
  types: ["audio/mpeg", "audio/wav", "audio/webm", "audio/mp4", "audio/ogg"],
};

function clone(status: VoiceClone["status"]): VoiceClone {
  return {
    id: "c1", status, provider: "elevenlabs", consent_version: "1", consent_text: "I, Rehan …",
    consent_signature: "Rehan Masood", consented_at: null, sample_count: 0, sample_bytes: 0,
    provider_state: null, error: null, ready_at: null, revoked_at: null, last_used_at: null,
  };
}

const SETTINGS: VoiceTwinSettings = {
  use_clone_for_calls: false, answer_inbound: false, inbound_number_linked: false,
  transfer_number: null, assistant_notes: null, paused: false, paused_at: null, paused_reason: null,
};

let calls: { url: string; init: RequestInit }[] = [];

beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify({}), {
      status: 200, headers: { "Content-Type": "application/json" },
    });
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function last() {
  return calls[calls.length - 1];
}

function header(name: string): string | undefined {
  const h = last().init.headers as Record<string, string>;
  return h[name];
}

describe("API body shapes", () => {
  it("consent sends the typed signature, own-voice tick, version and the EXACT text shown", async () => {
    await signVoiceConsent("  Rehan   Masood ", true, "1", "I, {name}, confirm. Signed {name}.");
    expect(last().url).toMatch(/\/me\/voice-clone\/consent$/);
    expect(last().init.method).toBe("POST");
    expect(JSON.parse(last().init.body as string)).toEqual({
      signature: "Rehan Masood", own_voice: true, consent_version: "1",
      consent_text: "I, Rehan Masood, confirm. Signed Rehan Masood.",
    });
  });

  it("a non-Latin-1 file name is percent-encoded, so fetch does not throw (L2)", async () => {
    const blob = new Blob([new Uint8Array([0x49, 0x44, 0x33])], { type: "audio/mp4" });
    await uploadVoiceSample(blob, "Voice Memo – Rehan.m4a");
    expect(header("X-Filename")).toBe("Voice%20Memo%20%E2%80%93%20Rehan.m4a");
    expect(() => new Headers({ "X-Filename": header("X-Filename")! })).not.toThrow();
  });

  it("a recording goes as a RAW body with its own audio type -- never JSON, never multipart", async () => {
    const blob = new Blob([new Uint8Array([0x49, 0x44, 0x33])], { type: "audio/webm;codecs=opus" });
    await uploadVoiceSample(blob, "me.webm");
    expect(last().url).toMatch(/\/me\/voice-clone\/samples$/);
    expect(last().init.body).toBe(blob);
    expect(header("Content-Type")).toBe("audio/webm");
    expect(header("X-Filename")).toBe("me.webm");
  });

  it("use-my-voice, settings, revoke and takeover use the right verbs", async () => {
    await setUseMyVoice(true);
    expect(last().init.method).toBe("PUT");
    expect(JSON.parse(last().init.body as string)).toEqual({ enabled: true });
    await saveVoiceTwinSettings({ answer_inbound: true });
    expect(last().url).toMatch(/\/voice-twin\/settings$/);
    expect(JSON.parse(last().init.body as string)).toEqual({ answer_inbound: true });
    await revokeVoiceClone();
    expect(last().url).toMatch(/\/me\/voice-clone$/);
    expect(last().init.method).toBe("DELETE");
    await takeOverCall("call-1");
    expect(last().url).toMatch(/\/calls\/call-1\/takeover$/);
    expect(last().init.method).toBe("POST");
    await getLiveCalls();
    expect(last().init.method).toBe("GET");
  });
});

describe("the consent-required state", () => {
  it("nothing can be uploaded before consent: no clone means the consent step", () => {
    expect(cloneStep({ feature_enabled: true, clone: null })).toBe("consent");
    expect(cloneStep({ feature_enabled: true, clone: clone("consented") })).toBe("upload");
    expect(cloneStep({ feature_enabled: false, clone: null })).toBe("disabled");
  });

  it("consent needs the own-voice tick and a typed name", () => {
    expect(consentError("Rehan Masood", false)).toMatch(/own voice/);
    expect(consentError(" ", true)).toMatch(/full name/);
    expect(consentError("Rehan Masood", true)).toBeNull();
    expect(consentBody("Rehan", true, "1", "{name}")).toEqual({
      signature: "Rehan", own_voice: true, consent_version: "1", consent_text: "Rehan" });
    expect(consentTextFor("I, {name}, agree.", "")).toBe("I, <your name>, agree.");
  });
});

describe("revoke and honest status", () => {
  it("revoked starts again at consent; revoke_pending is never shown as usable", () => {
    expect(cloneStep({ feature_enabled: true, clone: clone("revoked") })).toBe("consent");
    expect(cloneStep({ feature_enabled: true, clone: clone("revoke_pending") })).toBe("revoking");
    expect(statusLabel("revoke_pending")).toMatch(/retrying/);
    expect(statusLabel("training")).not.toMatch(/ready/i);
    expect(statusLabel("ready")).toBe("Ready");
  });

  it("verification, training and failure have their own steps", () => {
    expect(cloneStep({ feature_enabled: true, clone: clone("verifying") })).toBe("verify");
    expect(cloneStep({ feature_enabled: true, clone: clone("training") })).toBe("training");
    expect(cloneStep({ feature_enabled: true, clone: clone("failed") })).toBe("failed");
  });
});

describe("recordings", () => {
  it("type, size, count and total are checked like the server does", () => {
    const used = { count: 0, bytes: 0 };
    expect(sampleError({ size: 10, type: "application/pdf" }, LIMITS, used)).toMatch(/audio only/);
    expect(sampleError({ size: 30 * 1024 * 1024, type: "audio/mpeg" }, LIMITS, used)).toMatch(/at most 25 MB/);
    expect(sampleError({ size: 10, type: "audio/mpeg" }, LIMITS, { count: 25, bytes: 0 })).toMatch(/25 recordings/);
    expect(sampleError({ size: 10, type: "audio/webm;codecs=opus" }, LIMITS, used)).toBeNull();
    expect(baseType("audio/webm;codecs=opus")).toBe("audio/webm");
  });

  it("browser recording only where MediaRecorder and getUserMedia exist", () => {
    expect(canRecord({})).toBe(false);
    expect(canRecord({ MediaRecorder: function MR() {}, navigator: { mediaDevices: { getUserMedia: () => null } } })).toBe(true);
    expect(pickRecorderType((t) => t === "audio/mp4")).toBe("audio/mp4");
    expect(pickRecorderType(() => false)).toBeNull();
    expect(extensionFor("audio/webm;codecs=opus")).toBe("webm");
  });
});

describe("settings and the live banner", () => {
  it("only changed fields are sent", () => {
    expect(settingsBody({ answer_inbound: false, transfer_number: "", assistant_notes: "" }, SETTINGS)).toEqual({});
    expect(settingsBody({ answer_inbound: true, transfer_number: " +1 555 ", assistant_notes: "" }, SETTINGS))
      .toEqual({ answer_inbound: true, transfer_number: "+1 555" });
  });

  it("the banner shows live calls and says when your voice is used", () => {
    const live: LiveCall = { id: "1", direction: "inbound", status: "in_progress", voice_clone_used: true,
                             lead_id: null, who: "*******7777", started_at: null, can_take_over: true };
    expect(showLiveBanner([])).toBe(false);
    expect(showLiveBanner([live])).toBe(true);
    expect(liveCallText(live)).toBe("Your AI assistant is answering *******7777 in your voice.");
  });

  it("the banner never polls while AI calling is off, and polls faster during a call (L7)", () => {
    const live: LiveCall = { id: "1", direction: "outbound", status: "in_progress", voice_clone_used: false,
                             lead_id: "l", who: "Sara", started_at: null, can_take_over: false };
    expect(liveCallsPollMs({ calling_enabled: false, calls: [] })).toBe(false);
    expect(liveCallsPollMs({ calling_enabled: true, calls: [] })).toBe(60_000);
    expect(liveCallsPollMs({ calling_enabled: true, calls: [live] })).toBe(15_000);
  });
});
