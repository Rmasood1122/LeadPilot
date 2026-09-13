import { api } from "./client";
import type { Catalog } from "../pricing";

export interface Subscription {
  billing_model: "monthly" | "pay_per_meeting";
  tier: string;
  status: "incomplete" | "trialing" | "active" | "past_due" | "canceled";
  grants_plan: boolean;
  trial_ends_at: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  canceled_at: string | null;
  is_stub: boolean;
}

export interface BillingOverview {
  plan: string;
  subscription: Subscription | null;
  stub_mode: boolean;
  usage: {
    period_start: string;
    meetings_booked: number;
    amount_cents: number;
    by_status: Record<string, number>;
    price_per_meeting_cents: number;
    currency: string;
  };
}

export interface CheckoutResult {
  mode: "stub" | "stripe";
  checkout_url: string | null;
  subscription: Subscription | null;
}

export interface BillableMeetingRow {
  id: string;
  lead_id: string | null;
  strategy_id: string | null;
  source: string;
  amount_cents: number;
  currency: string;
  status: "pending" | "charged" | "waived" | "disputed" | "failed";
  occurred_at: string;
  charge_after: string;
  charged_at: string | null;
  is_stub: boolean;
  failure_reason: string | null;
  resolution_note: string | null;
}

export const billingApi = {
  catalog: () => api<Catalog>("/billing/catalog", { auth: false }),
  overview: () => api<BillingOverview>("/billing"),
  checkout: (billing_model: "monthly" | "pay_per_meeting", tier?: string) =>
    api<CheckoutResult>("/billing/checkout", { body: { billing_model, tier } }),
  cancel: () => api<Subscription>("/billing/cancel", { method: "POST" }),
  meetings: () => api<BillableMeetingRow[]>("/billing/meetings"),
  dispute: (id: string, reason: string) =>
    api<BillableMeetingRow>(`/billing/meetings/${id}/dispute`, { body: { reason } }),
};
