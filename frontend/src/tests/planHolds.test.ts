import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { planHoldNotice } from "@/lib/planHolds";

/** Messages held by the send-time plan check (app/services/plan_holds.py),
 *  reported by GET /strategies/{id}/campaign as `plan_holds`. */
describe("plan hold notice", () => {
  it("is absent when nothing is held", () => {
    expect(planHoldNotice(undefined)).toBeNull();
    expect(planHoldNotice({ count: 0, reasons: [] })).toBeNull();
  });

  it("says how many, why, and that an upgrade releases them", () => {
    const text = planHoldNotice({
      count: 2, reasons: ["Free plan does not include whatsapp channel. Allowed: gmail."],
    })!;
    expect(text).toMatch(/^2 messages are on hold because your current plan does not cover them\./);
    expect(text).toContain("Free plan does not include whatsapp channel.");
    expect(text).toMatch(/go out automatically within about 15 minutes/);
  });

  it("is rendered on the campaign overview", () => {
    const src = readFileSync("src/app/(app)/campaigns/page.tsx", "utf8");
    expect(src).toContain("planHoldNotice(campaign.plan_holds)");
    expect(src).toContain('data-testid="plan-hold-notice"');
  });
});
