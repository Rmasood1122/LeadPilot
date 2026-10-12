import { describe, expect, it } from "vitest";
import { ApiError } from "@/lib/api/client";
import { mvFailure, mvFailureText, mvShouldRetry } from "@/lib/multiVariate";

describe("multi-variate results panel (gaps-sweep-2 #9)", () => {
  it("a plan without multi_variate shows the upgrade line, not 'no data'", () => {
    const e = new ApiError(402, "plan limit");
    expect(mvFailure(e)).toBe("upgrade");
    expect(mvFailureText("upgrade")).toMatch(/Growth plan/);
    expect(mvShouldRetry(0, e)).toBe(false);
  });
  it("a foreign campaign is not found, and is not retried", () => {
    const e = new ApiError(404, "Strategy not found");
    expect(mvFailure(e)).toBe("not_found");
    expect(mvShouldRetry(0, e)).toBe(false);
  });
  it("other failures say so and retry a little", () => {
    const e = new Error("network");
    expect(mvFailure(e)).toBe("error");
    expect(mvShouldRetry(0, e)).toBe(true);
    expect(mvShouldRetry(2, e)).toBe(false);
    expect(mvFailure(null)).toBeNull();
  });
});
