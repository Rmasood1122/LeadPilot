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
  api_rate_limit_multiplier: number;
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

export interface Catalog {
  currency: string;
  trial_days: number;
  recommended: "monthly" | "pay_per_meeting";
  monthly: { id: "monthly"; name: string; recommended: boolean; tiers: MonthlyTier[] };
  pay_per_meeting: PayPerMeetingPlan;
}

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
