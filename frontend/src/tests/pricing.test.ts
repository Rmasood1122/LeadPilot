import { describe, expect, it } from "vitest";
import {
  breakEvenMeetings,
  channelList,
  checkoutNextStep,
  compareOptions,
  featureList,
  formatLimit,
  formatPrice,
  payPerMeetingCost,
  type PlanLimits,
} from "@/lib/pricing";

const LIMITS: PlanLimits = {
  max_strategies: 25, max_leads_per_strategy: 2500, max_sequence_steps: 15,
  channels: ["gmail", "whatsapp", "linkedin"], ab_testing: true, multi_variate: true,
  playbook_access: true, website_builder: true, max_site_pages: 25,
  analytics_history_days: 365, api_rate_limit_multiplier: 3,
};
const PPM = { monthly_fee_cents: 0, price_per_meeting_cents: 17_900 };

describe("formatting", () => {
  it("drops cents on whole-dollar prices and keeps them otherwise", () => {
    expect(formatPrice(14_900)).toBe("$149");
    expect(formatPrice(149_900)).toBe("$1,499");
    expect(formatPrice(17_950)).toBe("$179.50");
    expect(formatPrice(0)).toBe("$0");
  });
  it("reads -1 as unlimited", () => {
    expect(formatLimit(-1)).toBe("Unlimited");
    expect(formatLimit(10000)).toBe("10,000");
  });
  it("labels channels for humans", () => {
    expect(channelList(["gmail", "phone"])).toBe("Email · AI calls");
  });
});

describe("featureList", () => {
  it("is built only from enforced entitlements", () => {
    const list = featureList(LIMITS);
    expect(list).toContain("25 campaigns");
    expect(list).toContain("2,500 leads per campaign");
    expect(list).toContain("A/B + multi-variate testing");
    expect(list).toContain("365-day analytics history");
  });
  it("omits testing when the plan has none", () => {
    const list = featureList({ ...LIMITS, ab_testing: false, playbook_access: false,
                               analytics_history_days: -1 });
    expect(list.some((f) => f.includes("testing"))).toBe(false);
    expect(list).toContain("Unlimited analytics history");
  });
});

describe("monthly vs pay per meeting", () => {
  it("costs meetings times the per-meeting price plus the fee", () => {
    expect(payPerMeetingCost(3, PPM)).toBe(53_700);
    expect(payPerMeetingCost(-2, PPM)).toBe(0);
    expect(payPerMeetingCost(2.9, PPM)).toBe(17_900 * 2);
  });
  it("finds the break-even volume", () => {
    expect(breakEvenMeetings(34_900, 17_900)).toBe(2);
    expect(breakEvenMeetings(14_900, 17_900)).toBe(1);
    expect(breakEvenMeetings(14_900, 0)).toBe(Infinity);
  });
  it("says which is cheaper and by how much", () => {
    expect(compareOptions(1, { price_cents: 34_900 }, PPM))
      .toEqual({ monthly_cents: 34_900, pay_per_meeting_cents: 17_900,
                 cheaper: "pay_per_meeting", savings_cents: 17_000 });
    expect(compareOptions(5, { price_cents: 34_900 }, PPM).cheaper).toBe("monthly");
    expect(compareOptions(1, { price_cents: 17_900 }, PPM).cheaper).toBe("same");
  });
});

describe("checkoutNextStep", () => {
  it("redirects to Stripe when a checkout URL came back", () => {
    expect(checkoutNextStep({ mode: "stripe", checkout_url: "https://checkout.stripe.com/x" }))
      .toEqual({ kind: "redirect", url: "https://checkout.stripe.com/x" });
  });
  it("treats stub mode as already activated", () => {
    expect(checkoutNextStep({ mode: "stub", checkout_url: null })).toEqual({ kind: "activated" });
  });
});
