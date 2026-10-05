import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import {
  bulkSend, draftMessage, markMessageSent, saveMessage, sendMessageNow,
} from "@/lib/api/network";
import type { NetworkMessage } from "@/lib/api/network";
import {
  BULK_MAX, bulkCandidates, isReadyToSend, isSavable, messageErrorMessage, statusLabel,
  validateMessage,
} from "@/lib/linkedinNetwork";

let calls: { url: string; init: RequestInit }[] = [];
beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  }));
});
afterEach(() => { vi.unstubAllGlobals(); });

const msg = (over: Partial<NetworkMessage>): NetworkMessage => ({
  id: "m1", connection_id: "c1", product_id: "p1", text: "hi", status: "draft",
  channel: null, error: null, sent_at: null, ...over,
});

describe("wire", () => {
  it("uses the right verbs and bodies", async () => {
    await draftMessage("c1", "p1");
    await saveMessage("m1", "text");
    await markMessageSent("m1");
    await sendMessageNow("m1");
    await bulkSend(["m1", "m2"]);
    const seen = calls.map((c) => `${c.init.method} ${new URL(c.url).pathname}`);
    expect(seen).toEqual([
      "POST /linkedin-network/messages/draft",
      "PUT /linkedin-network/messages/m1",
      "POST /linkedin-network/messages/m1/mark-sent",
      "POST /linkedin-network/messages/m1/send",
      "POST /linkedin-network/messages/bulk-send",
    ]);
    expect(JSON.parse(calls[0].init.body as string)).toEqual({ connection_id: "c1", product_id: "p1" });
    expect(JSON.parse(calls[1].init.body as string)).toEqual({ text: "text" });
    expect(JSON.parse(calls[4].init.body as string)).toEqual({ ids: ["m1", "m2"] });
  });
});

describe("rules", () => {
  it("validates text", () => {
    expect(validateMessage("")).not.toBeNull();
    expect(validateMessage("x".repeat(1501))).not.toBeNull();
    expect(validateMessage("hello")).toBeNull();
  });
  it("only a saved message is ready to send", () => {
    expect(isReadyToSend(msg({ status: "draft" }))).toBe(false);
    expect(isReadyToSend(msg({ status: "approved" }))).toBe(true);
    expect(isReadyToSend(undefined)).toBe(false);
    expect(isSavable(msg({ status: "sent" }))).toBe(false);
    expect(isSavable(msg({ status: "failed" }))).toBe(true);
  });
  it("bulk takes only selected, saved messages, capped", () => {
    const all = [msg({ id: "a", status: "approved" }), msg({ id: "b", status: "draft" }),
                 msg({ id: "c", status: "sent" })];
    expect(bulkCandidates(all, new Set(["a", "b", "c"]))).toEqual(["a"]);
    expect(bulkCandidates(all, new Set())).toEqual([]);
    const many = Array.from({ length: 40 }, (_, i) => msg({ id: `m${i}`, status: "approved" }));
    expect(bulkCandidates(many, new Set(many.map((m) => m.id)))).toHaveLength(BULK_MAX);
  });
  it("maps errors and labels", () => {
    expect(messageErrorMessage(new ApiError(429, "x"))).toMatch(/Daily/);
    expect(messageErrorMessage(new ApiError(402, "x"))).toMatch(/Growth/);
    expect(messageErrorMessage(new ApiError(409, "Connect a LinkedIn account in Settings first."))).toMatch(/Connect/);
    expect(statusLabel(msg({ status: "sent", channel: "copy" }))).toBe("Sent by you");
    expect(statusLabel(msg({ status: "queued" }))).toBe("Queued");
  });
});
