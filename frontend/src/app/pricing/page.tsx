/**
 * app/pricing/page.tsx: the public pricing page at /pricing.
 *
 * A server component so the page carries its own title, description and
 * canonical URL, and so the plan names are in the exported HTML (StaticPlanList)
 * before the browser loads the live catalog. The interactive page (prices and
 * limits from GET /billing/catalog, checkout) is PricingClient.
 */

import type { Metadata } from "next";

import planNames from "@/content/plan-names.json";
import { Footer } from "@/components/Footer";
import { PRODUCT_FULL_NAME } from "@/lib/productFacts";
import { canonicalMeta } from "@/lib/seo/pageMeta";
import { staticPlans, type StaticPlan } from "@/lib/seo/staticPlans";

import { PricingClient } from "./PricingClient";

export const metadata: Metadata = {
  title: "LeadPilot by Calendarharvest pricing | Calendarharvest",
  description:
    `Plans for ${PRODUCT_FULL_NAME}: monthly plans (${planNames.monthly_tiers.join(", ")}), ` +
    `each with a free trial for a new account, or ${planNames.pay_per_meeting.toLowerCase()} booked.`,
  ...canonicalMeta("/pricing/"),
};

export default function PricingPage() {
  return <PricingClient footer={<Footer tone="theme" />} staticPlans={<StaticPlanList />} />;
}

function StaticPlanList() {
  const plans = staticPlans();
  return (
    <div className="mx-auto mb-8 grid max-w-4xl gap-6 md:grid-cols-[1.6fr_1fr]">
      <section aria-labelledby="static-monthly" className="rounded-xl border border-border bg-card p-6">
        <h2 id="static-monthly" className="text-xl font-semibold">Monthly subscription</h2>
        {plans.trialDays ? (
          <p className="text-sm text-muted-foreground">A {plans.trialDays}-day free trial for a new account.</p>
        ) : null}
        <ul className="mt-4 space-y-4">
          {plans.monthly.map((plan) => <PlanItem key={plan.name} plan={plan} />)}
        </ul>
      </section>
      <section aria-labelledby="static-ppm" className="rounded-xl border border-border bg-card p-6">
        <h2 id="static-ppm" className="text-xl font-semibold">{plans.payPerMeeting.name}</h2>
        <ul className="mt-4">
          <PlanItem plan={plans.payPerMeeting} hideName />
        </ul>
      </section>
    </div>
  );
}

function PlanItem({ plan, hideName = false }: { plan: StaticPlan; hideName?: boolean }) {
  return (
    <li>
      {!hideName && <h3 className="font-semibold">{plan.name}</h3>}
      {plan.tagline && <p className="text-sm text-muted-foreground">{plan.tagline}</p>}
      {plan.features.length > 0 && (
        <ul className="mt-1 list-disc pl-5 text-sm">
          {plan.features.map((f) => <li key={f}>{f}</li>)}
        </ul>
      )}
    </li>
  );
}
