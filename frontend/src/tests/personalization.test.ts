import { describe, expect, it } from "vitest";
import {
  fetchedAgo,
  formalityLabel,
  isLinkedInProfileUrl,
  isLoomShareUrl,
  sampleError,
} from "@/lib/personalization";

const SAMPLE = "Hey Sam, quick one — did the new rota land okay with the team? Cheers";

describe("sampleError", () => {
  it("mirrors the backend rules", () => {
    expect(sampleError([])).toMatch(/at least one/);
    expect(sampleError(["", "  "])).toMatch(/at least one/);
    expect(sampleError(["too short"])).toMatch(/Sample 1 is too short/);
    expect(sampleError([SAMPLE, "short"])).toMatch(/Sample 2/);
    expect(sampleError(Array(6).fill(SAMPLE))).toMatch(/At most 5/);
    expect(sampleError([SAMPLE, ""])).toBeNull();
  });
});

describe("url checks", () => {
  it("recognises Loom share links", () => {
    expect(isLoomShareUrl("https://www.loom.com/share/0123456789abcdef0123456789abcdef")).toBe(true);
    expect(isLoomShareUrl("https://www.loom.com/share/abc")).toBe(false);
    expect(isLoomShareUrl("https://vimeo.com/1")).toBe(false);
  });
  it("recognises LinkedIn profile links", () => {
    expect(isLinkedInProfileUrl("https://www.linkedin.com/in/sara-khan/")).toBe(true);
    expect(isLinkedInProfileUrl("https://www.linkedin.com/company/acme")).toBe(false);
  });
});

describe("labels", () => {
  it("formality", () => {
    expect(formalityLabel(1)).toBe("very casual");
    expect(formalityLabel(9)).toBe("very formal");
    expect(formalityLabel(null)).toBe("neutral");
  });
  it("fetchedAgo", () => {
    const now = new Date("2026-09-11T12:00:00Z");
    expect(fetchedAgo(null)).toBe("never");
    expect(fetchedAgo("2026-09-11T11:59:30Z", now)).toBe("just now");
    expect(fetchedAgo("2026-09-11T09:00:00Z", now)).toBe("3 hours ago");
    expect(fetchedAgo("2026-09-08T12:00:00Z", now)).toBe("3 days ago");
  });
});
