import { describe, it, expect } from "vitest";
import {
  failedPasses, latestPerPass, overrideOffer, reasonOk,
} from "@/lib/verificationReview";
import type { VerificationPass } from "@/lib/api/types";

const row = (pass_no: number, result: "PASS" | "FAIL", key = `k${pass_no}`,
             extra: Partial<VerificationPass> = {}): VerificationPass => ({
  pass_no, name: `P${pass_no}`, result, attempts: 1, key, ...extra,
});

describe("latestPerPass", () => {
  it("uses the last attempt of each pass", () => {
    const log = [row(1, "FAIL"), row(1, "PASS"), row(2, "FAIL"), row(2, "FAIL")];
    expect(latestPerPass(log).map((p) => [p.pass_no, p.result]))
      .toEqual([[1, "PASS"], [2, "FAIL"]]);
    expect(failedPasses(log).map((p) => p.pass_no)).toEqual([2]);
  });
});

describe("overrideOffer", () => {
  it("offers nothing when nothing failed", () => {
    expect(overrideOffer([row(1, "PASS")]).kind).toBe("none");
  });
  it("allows 1 to 3 failed checks", () => {
    for (const n of [1, 2, 3]) {
      const log = Array.from({ length: n }, (_, i) => row(i + 1, "FAIL"));
      expect(overrideOffer(log).kind).toBe("allowed");
    }
  });
  it("blocks 4 or more", () => {
    const log = [1, 2, 3, 5].map((n) => row(n, "FAIL"));
    expect(overrideOffer(log).kind).toBe("blocked");
  });
  it("never allows Legal & compliance, even alone", () => {
    const o = overrideOffer([row(4, "FAIL", "legal_compliance")]);
    expect(o.kind).toBe("blocked");
  });
  it("a legal pass that failed then passed does not block", () => {
    const log = [row(4, "FAIL", "legal_compliance"), row(4, "PASS", "legal_compliance"),
                 row(1, "FAIL")];
    expect(overrideOffer(log).kind).toBe("allowed");
  });
});

describe("reasonOk", () => {
  it("needs 20 real characters", () => {
    expect(reasonOk("short")).toBe(false);
    expect(reasonOk("   " + "x".repeat(19) + "   ")).toBe(false);
    expect(reasonOk("x".repeat(20))).toBe(true);
  });
});

import { latestCompleteRun, runOverrideOffer, splitRuns } from "@/lib/verificationReview";

const full = (failed: number[] = [1], keyOf = (n: number) => `k${n}`) =>
  Array.from({ length: 10 }, (_, i) => i + 1).flatMap((n) =>
    failed.includes(n)
      ? [row(n, "FAIL", keyOf(n), { attempt: 1 }), row(n, "FAIL", keyOf(n), { attempt: 2 })]
      : [row(n, "PASS", keyOf(n), { attempt: 1 })],
  );
const partial = (upto: number, failAt?: number, key = (n: number) => `k${n}`) =>
  Array.from({ length: upto }, (_, i) => i + 1).map((n) =>
    row(n, n === failAt ? "FAIL" : "PASS", key(n), { attempt: 1 }));
const keyL = (n: number) => (n === 4 ? "legal_compliance" : `k${n}`);

describe("run-aware review", () => {
  it("splits when the pass number goes backwards", () => {
    expect(splitRuns([...full(), ...partial(3), ...partial(4)]).map((r) => r.length))
      .toEqual([full().length, 3, 4]);
  });
  it("ignores partial runs after a complete one", () => {
    expect(latestCompleteRun([...full(), ...partial(4, 4)])).toEqual(full());
  });
  it("offers the sign-off from the complete run even if a later partial run shows legal failing", () => {
    const log = [...full([1], keyL), ...partial(4, 4, keyL)];
    const o = runOverrideOffer(log);
    expect(o.kind).toBe("allowed");
  });
  it("blocks when the complete run itself failed legal", () => {
    expect(runOverrideOffer(full([1, 4], keyL)).kind).toBe("blocked");
  });
  it("says so when no run completed", () => {
    expect(runOverrideOffer(partial(7, 1)).kind).toBe("blocked");
  });
});
