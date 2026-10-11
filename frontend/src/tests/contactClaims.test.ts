import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/** The contact page said LinkedIn is the primary outreach channel and that
 *  pricing is discussed on a call (help-center-discoveries D4). The code sends
 *  email by default (app/api/sequences.py SequenceCreate.channel = EMAIL;
 *  LinkedIn is a Growth-and-up plan channel, app/core/plans.py) and publishes
 *  every price on /pricing (GET /billing/catalog). */
describe("contact page matches the code (D4)", () => {
  const src = readFileSync("src/app/contact/page.tsx", "utf8");

  it("does not call LinkedIn the primary channel", () => {
    expect(src).not.toMatch(/LinkedIn is the primary/i);
    expect(src).toMatch(/Email is the default channel/);
  });

  it("makes no unmeasured results timeline and no self-serve contradiction", () => {
    expect(src).not.toMatch(/4–6 weeks|4-6 weeks|4–8 week|4-8 week/);
    expect(src).not.toMatch(/self-serve tool/i);
  });

  it("names the plans that include LinkedIn, Pay per meeting among them", () => {
    expect(src).toMatch(/Growth, Scale, Enterprise and Pay per meeting plans/);
  });

  it("does not hide pricing behind a call", () => {
    expect(src).not.toMatch(/Pricing is discussed on the call/i);
    expect(src).toMatch(/published on the Pricing page/);
  });
});
