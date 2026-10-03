/**
 * Regression guard for the double-stringify bug documented at the bottom of
 * src/lib/api/client.ts.
 *
 * `api()` stringifies `opts.body` itself. A module that passes
 * `body: JSON.stringify(payload)` therefore sends a JSON *string*
 * (`"\"{...}\""`), FastAPI answers 422, and the feature is broken in a way no
 * type-check and no backend test can see. Every apiClient write in the app was
 * once broken exactly this way.
 *
 * These tests call the write helpers added by Part 1 and assert that what goes
 * on the wire parses to an OBJECT.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { approveSendReview, rejectSendReview } from "@/lib/api/sendReview";
import { setReplyHandled, setThreadHandled } from "@/lib/api/inbox";

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

function sentBody(): unknown {
  const raw = calls[calls.length - 1].init.body;
  expect(typeof raw).toBe("string");
  return JSON.parse(raw as string);
}

describe("write helpers send a JSON object, not a JSON string", () => {
  it("approveSendReview", async () => {
    await approveSendReview("r1", { note: "looks fine", body: "edited copy" });
    expect(sentBody()).toEqual({ note: "looks fine", body: "edited copy" });
  });

  it("approveSendReview with no payload still sends an object", async () => {
    await approveSendReview("r1");
    expect(sentBody()).toEqual({});
  });

  it("rejectSendReview", async () => {
    await rejectSendReview("r1", "Wrong moment for this account");
    expect(sentBody()).toEqual({ note: "Wrong moment for this account" });
  });

  it("setThreadHandled", async () => {
    await setThreadHandled("l1", true);
    expect(sentBody()).toEqual({ handled: true });
  });

  it("setThreadHandled(false) puts a thread back", async () => {
    await setThreadHandled("l1", false);
    expect(sentBody()).toEqual({ handled: false });
  });

  it("setReplyHandled", async () => {
    await setReplyHandled("rep1");
    expect(sentBody()).toEqual({ handled: true });
  });
});

describe("the requests reach the documented paths", () => {
  it("uses POST and the feature's own prefix", async () => {
    await setThreadHandled("l1");
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].url).toContain("/inbox/l1/handled");
    await rejectSendReview("r1", "a real reason");
    expect(calls[1].url).toContain("/send-reviews/r1/reject");
  });

  it("escapes an id that is not URL-safe", async () => {
    await setReplyHandled("a/b");
    expect(calls[0].url).toContain("/inbox/replies/a/b/handled");
  });
});
