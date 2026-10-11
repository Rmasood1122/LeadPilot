/** Pricing page logic (Section E) — pure, so it is unit-tested in
 *  src/tests/pricing.test.ts. Every number rendered comes from the backend's
 *  GET /billing/catalog (app/core/billing_catalog.py); nothing here hardcodes
 *  a price. */

export interface PlanLimits {
  max_strategies: number;
  max_leads_per_strategy: number;
  max_sequence_steps: number;
  channels: string[];
  ab_testing: boolean;
  multi_variate: boolean;
  playbook_access: boolean;
  website_builder: boolean;
  max_site_pages: number;
  analytics_history_days: number;
}

export interface MonthlyTier {
  id: string;
  name: string;
  price_cents: number;
  tagline: string;
  plan: string;
  trial_days: number;
  limits: PlanLimits;
}

export interface PayPerMeetingPlan {
  id: "pay_per_meeting";
  name: string;
  monthly_fee_cents: number;
  price_per_meeting_cents: number;
  grace_hours: number;
  tagline: string;
  recommended: boolean;
  limits: PlanLimits;
}

/** One tier billed yearly (present only while the backend offers annual
 *  billing). annual_price_cents = monthly price x months_charged, decided in
 *  app/core/billing_catalog.py (ANNUAL_MONTHS_CHARGED) — never here. */
export interface AnnualTier {
  id: string;
  name: string;
  tagline: string;
  plan: string;
  monthly_price_cents: number;
  annual_price_cents: number;
  monthly_equivalent_cents: number;
  savings_cents: number;
  months_charged: number;
  trial_days: number;
  limits: PlanLimits;
}

export interface Catalog {
  currency: string;
  trial_days: number;
  annual_available?: boolean;
  renewal_disclosure_version?: string;
  recommended: "monthly" | "pay_per_meeting";
  monthly: { id: "monthly"; name: string; recommended: boolean; tiers: MonthlyTier[] };
  annual?: {
    id: "annual"; name: string; months_charged: number; term_months: number;
    renewal_notice_days: number; tiers: AnnualTier[];
  };
  pay_per_meeting: PayPerMeetingPlan;
}

export type BillingInterval = "monthly" | "annual";
export type CheckoutModel = "monthly" | "annual" | "pay_per_meeting";

/** 14900 -> "$149"; 17950 -> "$179.50". Whole dollars drop the cents. */
export function formatPrice(cents: number, currency = "usd"): string {
  const amount = (cents ?? 0) / 100;
  const whole = Number.isInteger(amount);
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency", currency: currency.toUpperCase(),
      minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: whole ? 0 : 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(whole ? 0 : 2)} ${currency.toUpperCase()}`;
  }
}

/** -1 is the backend's "unlimited". */
export function formatLimit(value: number): string {
  if (value === -1) return "Unlimited";
  return new Intl.NumberFormat("en-US").format(value);
}

const CHANNEL_LABELS: Record<string, string> = {
  gmail: "Email", whatsapp: "WhatsApp", linkedin: "LinkedIn", phone: "AI calls",
};

export function channelList(channels: string[]): string {
  return channels.map((c) => CHANNEL_LABELS[c] ?? c).join(" · ");
}

/** The bullet list for one plan, built only from enforced entitlements. */
export function featureList(limits: PlanLimits): string[] {
  const out = [
    `${formatLimit(limits.max_strategies)} campaigns`,
    `${formatLimit(limits.max_leads_per_strategy)} leads per campaign`,
    `${formatLimit(limits.max_sequence_steps)} sequence steps`,
    channelList(limits.channels),
  ];
  if (limits.ab_testing) out.push(limits.multi_variate ? "A/B + multi-variate testing" : "A/B testing");
  if (limits.playbook_access) out.push("Self-learning playbook");
  out.push(limits.analytics_history_days === -1
    ? "Unlimited analytics history"
    : `${limits.analytics_history_days}-day analytics history`);
  return out;
}

/** Booked meetings per month at which a monthly tier costs the same as paying
 *  per meeting. Above it, monthly is cheaper. */
export function breakEvenMeetings(monthlyCents: number, perMeetingCents: number): number {
  if (perMeetingCents <= 0) return Infinity;
  return Math.ceil(monthlyCents / perMeetingCents);
}

export function payPerMeetingCost(meetings: number, plan: Pick<PayPerMeetingPlan,
  "monthly_fee_cents" | "price_per_meeting_cents">): number {
  return plan.monthly_fee_cents + Math.max(0, Math.floor(meetings)) * plan.price_per_meeting_cents;
}

/** For an expected meeting volume: which option is cheaper, and by how much. */
export function compareOptions(meetings: number, tier: Pick<MonthlyTier, "price_cents">,
  plan: Pick<PayPerMeetingPlan, "monthly_fee_cents" | "price_per_meeting_cents">) {
  const ppm = payPerMeetingCost(meetings, plan);
  const monthly = tier.price_cents;
  return {
    monthly_cents: monthly,
    pay_per_meeting_cents: ppm,
    cheaper: monthly < ppm ? "monthly" as const : ppm < monthly ? "pay_per_meeting" as const : "same" as const,
    savings_cents: Math.abs(monthly - ppm),
  };
}

/** What a checkout call should do with its response. */
export function checkoutNextStep(res: { mode: "stub" | "stripe"; checkout_url: string | null }):
  { kind: "redirect"; url: string } | { kind: "activated" } {
  if (res.mode === "stripe" && res.checkout_url) return { kind: "redirect", url: res.checkout_url };
  return { kind: "activated" };
}

/** "June 3, 2026" for a Date (UTC, so the page and the emails agree). */
export function formatDate(date: Date): string {
  return date.toLocaleDateString("en-US", {
    year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
  });
}

/** The version of the disclosure wording below. Echoed to the backend with
 *  the consent; MUST equal app/core/billing_catalog.py DISCLOSURE_VERSION
 *  (tests/test_annual_billing_review.py pins it). Bump both when the
 *  wording changes. */
export const RENEWAL_DISCLOSURE_VERSION = "2026-10-11.2";

/** The trial a subscription checkout started now would get — decided by the
 *  BACKEND (GET /billing/checkout-terms), never guessed here. */
export interface CheckoutTerms {
  trial_eligible: boolean;
  trial_days: number;
  trial_ends_at: string | null;
  pilot_extended: boolean;
  pilot_verdict_at: string | null;
  first_charge_at: string;
  disclosure_version: string;
  annual_locked_until?: string | null;
}

/** The terms of a brand-new account (no trial used, no pilot): what a
 *  signed-out visitor would get after signing up. A fact, not a guess. */
export function newAccountTerms(trialDays: number, now: Date): CheckoutTerms {
  const end = new Date(now.getTime() + Math.max(0, trialDays) * 86_400_000).toISOString();
  return {
    trial_eligible: trialDays > 0, trial_days: trialDays,
    trial_ends_at: trialDays > 0 ? end : null, pilot_extended: false, pilot_verdict_at: null,
    first_charge_at: trialDays > 0 ? end : now.toISOString(),
    disclosure_version: RENEWAL_DISCLOSURE_VERSION,
  };
}

/** The auto-renewal disclosure shown next to the consent checkbox, BEFORE the
 *  customer is sent to payment (docs/features/annual-billing.md, Compliance:
 *  amount, first charge, renewal term, how to cancel). Every date is the
 *  backend's. Pure, so the exact words are tested. */
export function renewalDisclosure(args: {
  interval: BillingInterval;
  tierName: string;
  amountCents: number;
  currency: string;
  terms: CheckoutTerms;
}): string {
  const amount = formatPrice(args.amountCents, args.currency);
  const term = args.interval === "annual" ? "year" : "month";
  const plan = `${args.tierName} ${args.interval === "annual" ? "annual" : "monthly"}`;
  const t = args.terms;
  const trialEnd = t.trial_ends_at ? `${formatDate(new Date(t.trial_ends_at))} (UTC)` : null;
  let start: string;
  if (t.pilot_extended && trialEnd) {
    start = `${amount} is charged on ${trialEnd}, when your free trial ends — it runs until your 30-day pilot's verdict`;
  } else if (trialEnd) {
    start = `${amount} is charged on ${trialEnd}, when your ${t.trial_days}-day free trial ends`;
  } else {
    start = `${amount} is charged today (this account has already had its free trial)`;
  }
  const refunds = args.interval === "annual"
    ? " Cancelling stops the next renewal; a year already paid is not refunded."
    : "";
  return `${plan}: ${start}, then ${amount} every ${term} on that date until you cancel. ` +
    `It renews automatically. Cancel anytime online in Profile → Plan → Cancel plan; you keep ` +
    `your plan until the end of the period you paid for.${refunds}`;
}

/** The checkout button says what will happen, from the same terms. */
export function checkoutButtonLabel(terms: CheckoutTerms, tierName: string,
  interval: BillingInterval): string {
  const suffix = interval === "annual" ? " (annual)" : "";
  if (terms.pilot_extended && terms.trial_ends_at) {
    return `Start free trial of ${tierName}${suffix} until ${formatDate(new Date(terms.trial_ends_at))}`;
  }
  if (terms.trial_ends_at) return `Start ${terms.trial_days}-day trial of ${tierName}${suffix}`;
  return `Subscribe to ${tierName}${suffix}`;
}

/** The body POST /billing/checkout expects. Every auto-renewing plan
 *  (monthly and annual) carries the consent and the disclosure version the
 *  backend requires (422 / 409 without them). */
export function checkoutPayload(model: CheckoutModel, tier: string | undefined,
  acceptRenewalTerms: boolean): {
    billing_model: CheckoutModel; tier?: string; accept_renewal_terms?: boolean;
    disclosure_version?: string;
  } {
  if (model === "pay_per_meeting") return { billing_model: model };
  return { billing_model: model, tier, accept_renewal_terms: acceptRenewalTerms,
           disclosure_version: RENEWAL_DISCLOSURE_VERSION };
}

/** The subscription fields the Plan card needs (a subset of /billing). */
export interface SubscriptionView {
  billing_model: CheckoutModel;
  tier: string;
  status: string;
  grants_plan: boolean;
  trial_ends_at: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  is_stub?: boolean;
  price_cents?: number | null;
  interval?: "month" | "year" | null;
  needs_support?: boolean;
}

const MODEL_LABELS: Record<string, string> = {
  monthly: "Monthly", annual: "Annual", pay_per_meeting: "Pay per meeting",
};

/** One line for the Plan card: what you pay and what happens next. */
export function subscriptionSummary(sub: SubscriptionView | null | undefined,
  currency = "usd"): string | null {
  if (!sub) return null;
  const model = MODEL_LABELS[sub.billing_model] ?? sub.billing_model;
  const per = (sub.interval ?? (sub.billing_model === "annual" ? "year" : "month")) === "year"
    ? "year" : "month";
  const price = sub.price_cents != null
    ? ` · ${formatPrice(sub.price_cents, currency)} per ${per}`
    : "";
  const fmt = (iso: string | null) => (iso ? formatDate(new Date(iso)) : null);
  if (!sub.grants_plan) return `${model} · ${sub.status}`;
  if (sub.status === "past_due") {
    return `${model}${price} · Payment failed — the card is being retried`;
  }
  if (sub.cancel_at_period_end) {
    return `${model}${price} · Cancelled — access until ${fmt(sub.current_period_end) ?? "the end of the period"}`;
  }
  if (sub.status === "trialing" && sub.trial_ends_at) {
    return `${model}${price} · Free trial until ${fmt(sub.trial_ends_at)}, then renews automatically`;
  }
  if (sub.billing_model === "pay_per_meeting") return `${model} · Billed per booked meeting`;
  const next = fmt(sub.current_period_end);
  return `${model}${price} · Renews automatically${next ? ` on ${next}` : ""}`;
}

/** The Cancel plan button shows only when there is something to cancel. */
export function canCancel(sub: SubscriptionView | null | undefined): boolean {
  return !!sub && sub.grants_plan && !sub.cancel_at_period_end;
}

/** What the confirm step says will happen. */
export function cancelConsequence(sub: SubscriptionView): string {
  if (sub.billing_model === "pay_per_meeting") {
    return "Pay per meeting stops now. Meetings already booked are still billed.";
  }
  if (sub.is_stub) return "Your plan ends now and the account returns to Free.";
  if (sub.status === "past_due") {
    return "Your last payment failed. Cancelling ends the plan now and cancels the unpaid " +
      "invoice, so nothing more is charged. The account returns to Free.";
  }
  const until = sub.status === "trialing" ? sub.trial_ends_at : sub.current_period_end;
  return `Your plan will not renew. You keep it until ${until ? formatDate(new Date(until)) : "the end of the current period"}, then the account returns to Free.`;
}
