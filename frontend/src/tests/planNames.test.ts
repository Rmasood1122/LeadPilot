/**
 * The pricing page's static plan names (src/content/plan-names.json, rendered
 * for crawlers that do not run JavaScript) must be exactly the names the
 * backend sells (app/core/billing_catalog.py), in the same order.
 */
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import planNames from "@/content/plan-names.json";

describe("static plan names match the billing catalog", () => {
  it("lists every tier and the pay-per-meeting plan, in catalog order", () => {
    const source = readFileSync("../app/core/billing_catalog.py", "utf8");
    // MONTHLY_TIERS and PAY_PER_MEETING_PLAN only (not the subscription labels).
    const start = source.indexOf("MONTHLY_TIERS: list");
    const end = source.indexOf("_TIERS = {", start);
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const catalog = source.slice(start, end);
    const names = [...catalog.matchAll(/^\s+"name": "([^"]+)",$/gm)].map((m) => m[1]);
    expect(names.length).toBeGreaterThan(0);
    expect([...planNames.monthly_tiers, planNames.pay_per_meeting]).toEqual(names);
  });
});
