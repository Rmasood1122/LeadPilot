/** F06 Quickstart — pure helpers and the API write bodies. */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  STAGES,
  formatDuration,
  icpSummary,
  isInProgress,
  normalizeWebsite,
  offerError,
  stageIndex,
  visibleDrafts,
  type QuickstartDraft,
} from "@/lib/quickstart";
import { discardQuickstartDraft, startQuickstart } from "@/lib/api/quickstart";

describe("normalizeWebsite", () => {
  it.each([
    ["example.com", "https://example.com/"],
    ["http://example.com/about", "https://example.com/about"],
    ["  https://www.example.com/#x ", "https://www.example.com/"],
  ])("%s -> %s", (input, expected) => {
    expect(normalizeWebsite(input)).toBe(expected);
  });

  it.each([
    "", "not a url", "ftp://example.com", "https://user:pw@example.com",
    "https://example.com:8080", "intranet", "javascript:alert(1)",
  ])("refuses %s", (input) => {
    expect(normalizeWebsite(input)).toBeNull();
  });
});

describe("offerError", () => {
  it("wants one real line", () => {
    expect(offerError("short")).toMatch(/at least/);
    expect(offerError("x".repeat(301))).toMatch(/at most/);
    expect(offerError("Automated inspection reports for fire contractors")).toBeNull();
  });

  it("counts folded whitespace, like the server", () => {
    expect(offerError("  a    b    c  ")).not.toBeNull();
  });
});

describe("stages", () => {
  it("are in the order the run moves through them", () => {
    expect(STAGES.map((s) => s.status)).toEqual(
      ["fetching", "extracting", "sourcing", "drafting", "ready"]);
    expect(stageIndex("queued")).toBe(-1);
    expect(stageIndex("drafting")).toBe(3);
  });

  it("only ready and failed are terminal", () => {
    expect(isInProgress("sourcing")).toBe(true);
    expect(isInProgress("queued")).toBe(true);
    expect(isInProgress("ready")).toBe(false);
    expect(isInProgress("failed")).toBe(false);
  });
});

describe("formatDuration", () => {
  it.each([
    [null, "—"], [undefined, "—"], [-1, "—"], [52, "52s"], [245, "4m 05s"],
    [900, "15m 00s"], [3720, "1h 02m"],
  ])("%s -> %s", (seconds, expected) => {
    expect(formatDuration(seconds as number | null | undefined)).toBe(expected);
  });
});

describe("visibleDrafts / icpSummary", () => {
  const draft = (id: string, status: "draft" | "discarded"): QuickstartDraft => ({
    id, run_id: "r", status, label: "Quickstart draft — full research running",
    subject: "s", body: "b", claims_changed: 0, lead: null, created_at: null,
  });

  it("hides discarded drafts unless asked", () => {
    const drafts = [draft("a", "draft"), draft("b", "discarded")];
    expect(visibleDrafts(drafts).map((d) => d.id)).toEqual(["a"]);
    expect(visibleDrafts(drafts, true).map((d) => d.id)).toEqual(["a", "b"]);
    expect(visibleDrafts(undefined)).toEqual([]);
  });

  it("summarises the ICP in one line", () => {
    expect(icpSummary({ titles: ["Owner", "COO"], industries: ["fire protection"],
                        locations: [] })).toBe("Owner, COO · fire protection");
    expect(icpSummary(null)).toBe("");
  });
});

describe("write helpers send a JSON object, not a JSON string", () => {
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

  it("startQuickstart", async () => {
    await startQuickstart({ website_url: "https://example.com/", offer: "One line offer here" });
    const last = calls[calls.length - 1];
    expect(last.url).toMatch(/\/quickstart$/);
    expect(last.init.method).toBe("POST");
    expect(JSON.parse(last.init.body as string)).toEqual(
      { website_url: "https://example.com/", offer: "One line offer here" });
  });

  it("discardQuickstartDraft", async () => {
    await discardQuickstartDraft("d1");
    const last = calls[calls.length - 1];
    expect(last.url).toMatch(/\/quickstart\/drafts\/d1\/discard$/);
    expect(JSON.parse(last.init.body as string)).toEqual({});
  });
});
