import { describe, expect, it } from "vitest";
import { usageFraction } from "@/lib/api/linkedin";

describe("usageFraction", () => {
  it("clamps to 0..1 and treats a zero limit as full", () => {
    expect(usageFraction(5, 20)).toBe(0.25);
    expect(usageFraction(25, 20)).toBe(1);
    expect(usageFraction(-1, 20)).toBe(0);
    expect(usageFraction(0, 0)).toBe(1);
  });
});
