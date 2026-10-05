import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import {
  applyInterview, discardInterview, finishInterview, saveAnswers, snoozeInterview, startInterview,
} from "@/lib/api/interview";
import type { StyleProfile } from "@/lib/api/interview";
import {
  appendTranscript, canFinish, formToProfile, interviewErrorMessage, profileToForm, speechSupported,
  usableAnswers,
} from "@/lib/interview";

let calls: { url: string; init: RequestInit }[] = [];
beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  }));
});
afterEach(() => { vi.unstubAllGlobals(); });

const P: StyleProfile = {
  tone: "warm", formality: 2, vocabulary_level: "conversational", sentence_length: "short",
  avg_words_per_sentence: 9, humor: "light", greeting_style: "Hey", signoff_style: "Cheers",
  signature_habits: ["dashes"], do: ["be brief"], dont: ["jargon"], summary: "Short.",
};

describe("wire", () => {
  it("uses the right verbs and bodies", async () => {
    await startInterview("voice", true);
    await saveAnswers("i1", [{ index: 0, text: "hello" }]);
    await finishInterview("i1");
    await applyInterview("i1");
    await applyInterview("i1", P);
    await discardInterview("i1");
    await snoozeInterview(7);
    const seen = calls.map((c) => `${c.init.method} ${new URL(c.url).pathname}`);
    expect(seen).toEqual([
      "POST /interview/start", "PUT /interview/i1/answers", "POST /interview/i1/finish",
      "POST /interview/i1/apply", "POST /interview/i1/apply", "POST /interview/i1/discard",
      "POST /interview/snooze",
    ]);
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ mode: "voice", voice_notice_ack: true });
    expect(JSON.parse(calls[3].init.body as string)).toEqual({});
    expect(JSON.parse(calls[4].init.body as string)).toEqual({ profile: P });
    expect(JSON.parse(calls[6].init.body as string)).toEqual({ days: 7 });
  });
});

describe("rules", () => {
  it("needs three real answers", () => {
    const long = "x".repeat(40);
    expect(usableAnswers([long, "short", long])).toBe(2);
    expect(canFinish([long, long, "no"])).toBe(false);
    expect(canFinish([long, long, long])).toBe(true);
  });
  it("detects browser speech support", () => {
    expect(speechSupported({})).toBe(false);
    expect(speechSupported({ webkitSpeechRecognition: function () {} })).toBe(true);
    expect(speechSupported({ SpeechRecognition: function () {} })).toBe(true);
    expect(speechSupported(undefined)).toBe(false);
  });
  it("appends dictation without gluing words", () => {
    expect(appendTranscript("", " hello ")).toBe("hello");
    expect(appendTranscript("one two  ", "three")).toBe("one two three");
    expect(appendTranscript("keep", "   ")).toBe("keep");
  });
  it("round-trips the editable fields and clamps formality", () => {
    const f = profileToForm(P);
    expect(f.do).toBe("be brief");
    const edited = formToProfile(P, { ...f, tone: " calm ", formality: 9, do: "a\n\n b \n", dont: "" });
    expect(edited.tone).toBe("calm");
    expect(edited.formality).toBe(5);
    expect(edited.do).toEqual(["a", "b"]);
    expect(edited.dont).toEqual([]);
    expect(edited.humor).toBe("light");           // not editable: stays as proposed
  });
  it("maps errors", () => {
    expect(interviewErrorMessage(new ApiError(429, "x"))).toMatch(/Too many/);
    expect(interviewErrorMessage(new ApiError(422, "Answer at least 3"))).toBe("Answer at least 3");
    expect(interviewErrorMessage(new Error("boom"))).toMatch(/Try again/);
  });
});
