import { describe, expect, it } from "vitest";
import {
  breakEvenMeetings,
  canCancel,
  cancelConsequence,
  channelList,
  checkoutNextStep,
  checkoutPayload,
  compareOptions,
  featureList,
  checkoutButtonLabel,
  newAccountTerms,
  planSwitchNotice,
  RENEWAL_DISCLOSURE_VERSION,
  formatDate,
  formatLimit,
  formatPrice,
  payPerMeetingCost,
  renewalDisclosure,
  subscriptionSummary,
  type PlanLimits,
} from "@/lib/pricing";

const LIMITS: PlanLimits = {
  max_strategies: 25, max_leads_per_strategy: 2500, max_sequence_steps: 15,
  channels: ["gmail", "whatsapp", "linkedin"], ab_testing: true, multi_variate: true,
  playbook_access: true, website_builder: true, max_site_pages: 25,
  analytics_history_days: 365,
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

// --------------------------------------------------------------------------
// Annual billing (docs/features/annual-billing.md)
// --------------------------------------------------------------------------

describe("renewal disclosure driven by the backend's terms", () => {
  const NOW = new Date(Date.UTC(2026, 9, 11, 12));   // 11 Oct 2026
  const fresh = newAccountTerms(14, NOW);
  const used = { ...fresh, trial_eligible: false, trial_days: 0, trial_ends_at: null,
    first_charge_at: NOW.toISOString() };
  const pilot = { ...fresh, pilot_extended: true,
    trial_ends_at: "2026-11-12T00:00:00+00:00", first_charge_at: "2026-11-12T00:00:00+00:00",
    pilot_verdict_at: "2026-11-12T00:00:00+00:00" };

  it("states the annual amount, first charge, renewal term, how to cancel and no refund", () => {
    const text = renewalDisclosure({ interval: "annual", tierName: "Growth",
      amountCents: 349_000, currency: "usd", terms: fresh });
    expect(text).toContain("Growth annual");
    expect(text).toContain("$3,490 is charged on October 25, 2026 (UTC), when your 14-day free trial ends");
    expect(text).toContain("then $3,490 every year on that date until you cancel");
    expect(text).toContain("renews automatically");
    expect(text).toContain("Profile → Plan → Cancel plan");
    expect(text).toContain("not refunded");
  });

  it("a used trial is charged today — never a trial the backend will not give", () => {
    const text = renewalDisclosure({ interval: "monthly", tierName: "Starter",
      amountCents: 14_900, currency: "usd", terms: used });
    expect(text).toContain("$149 is charged today (this account has already had its free trial)");
    expect(text).toContain("every month");
    expect(text).not.toContain("free trial ends");
    expect(text).not.toContain("refunded");
    expect(checkoutButtonLabel(used, "Starter", "monthly")).toBe("Subscribe to Starter");
  });

  it("a pilot-extended trial names the verdict date", () => {
    const text = renewalDisclosure({ interval: "monthly", tierName: "Growth",
      amountCents: 34_900, currency: "usd", terms: pilot });
    expect(text).toContain("$349 is charged on November 12, 2026 (UTC), when your free trial ends — it runs until your 30-day pilot's verdict");
    expect(checkoutButtonLabel(pilot, "Growth", "annual"))
      .toBe("Start free trial of Growth (annual) until November 12, 2026");
    expect(checkoutButtonLabel(fresh, "Growth", "monthly")).toBe("Start 14-day trial of Growth");
  });

  it("every auto-renewing checkout carries consent and the disclosure version", () => {
    expect(checkoutPayload("annual", "growth", true)).toEqual({ billing_model: "annual",
      tier: "growth", accept_renewal_terms: true, disclosure_version: RENEWAL_DISCLOSURE_VERSION });
    expect(checkoutPayload("monthly", "growth", true)).toEqual({ billing_model: "monthly",
      tier: "growth", accept_renewal_terms: true, disclosure_version: RENEWAL_DISCLOSURE_VERSION });
    expect(checkoutPayload("pay_per_meeting", undefined, false)).toEqual(
      { billing_model: "pay_per_meeting" });
  });

  it("a new account's terms are a 14-day trial with no pilot", () => {
    expect(fresh.trial_eligible).toBe(true);
    expect(formatDate(new Date(fresh.trial_ends_at!))).toBe("October 25, 2026");
    expect(fresh.disclosure_version).toBe(RENEWAL_DISCLOSURE_VERSION);
  });
});

describe("plan card", () => {
  const base = { billing_model: "annual" as const, tier: "growth", status: "active",
    grants_plan: true, trial_ends_at: null, current_period_end: "2027-10-25T00:00:00+00:00",
    cancel_at_period_end: false, price_cents: 349_000 };

  it("summarises what is paid and when it renews", () => {
    expect(subscriptionSummary(base)).toBe(
      "Annual · $3,490 per year · Renews automatically on October 25, 2027");
    expect(subscriptionSummary({ ...base, status: "trialing",
      trial_ends_at: "2026-10-25T00:00:00+00:00" })).toBe(
      "Annual · $3,490 per year · Free trial until October 25, 2026, then renews automatically");
    expect(subscriptionSummary({ ...base, cancel_at_period_end: true })).toBe(
      "Annual · $3,490 per year · Cancelled — access until October 25, 2027");
    expect(subscriptionSummary(null)).toBeNull();
  });

  it("offers Cancel plan only when there is something to cancel", () => {
    expect(canCancel(base)).toBe(true);
    expect(canCancel({ ...base, cancel_at_period_end: true })).toBe(false);
    expect(canCancel({ ...base, grants_plan: false, status: "canceled" })).toBe(false);
    expect(canCancel(null)).toBe(false);
  });

  it("says what cancelling does before it happens", () => {
    expect(cancelConsequence(base)).toBe(
      "Your plan will not renew. You keep it until October 25, 2027, then the account returns to Free.");
    expect(cancelConsequence({ ...base, billing_model: "pay_per_meeting" })).toMatch(/stops now/);
    expect(cancelConsequence({ ...base, is_stub: true })).toMatch(/ends now/);
    expect(cancelConsequence({ ...base, status: "past_due" })).toBe(
      "Your last payment failed. Cancelling ends the plan now and cancels the unpaid " +
      "invoice, so nothing more is charged. The account returns to Free.");
    expect(subscriptionSummary({ ...base, status: "past_due" }))
      .toBe("Annual · $3,490 per year · Payment failed — the card is being retried");
  });
});

describe("plan switch notice (gaps-sweep-2 #15)", () => {
  const sub = (o: Partial<{ billing_model: string; tier: string; status: string; is_stub: boolean }>) =>
    ({ billing_model: "monthly", tier: "growth", status: "active", is_stub: false, ...o });
  it("says a paid monthly plan is cancelled with no refund before checkout", () => {
    const text = planSwitchNotice(sub({}));
    expect(text).toMatch(/cancels it as soon as the new checkout is completed/);
    expect(text).toMatch(/not refunded or credited/);
  });
  it("a trial ends; nothing was paid so nothing is said about refunds", () => {
    const text = planSwitchNotice(sub({ status: "trialing" }));
    expect(text).toMatch(/free trial/);
    expect(text).not.toMatch(/refund/);
  });
  it("nothing to say without a live subscription", () => {
    expect(planSwitchNotice(null)).toBeNull();
    expect(planSwitchNotice(sub({ billing_model: "pay_per_meeting" }))).toBeNull();
    expect(planSwitchNotice(sub({ status: "canceled" }))).toBeNull();
    expect(planSwitchNotice(sub({ is_stub: true }))).toBeNull();
  });
});
