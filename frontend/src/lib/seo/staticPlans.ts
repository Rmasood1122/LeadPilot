/**
 * The plans the pricing page renders as static HTML, for crawlers that do not
 * run JavaScript. Server-only: read at build time.
 *
 * Source, in order of preference:
 *   1. src/content/plans-snapshot.json, a copy of the live GET /billing/catalog
 *      written by scripts/seo/snapshot_plans.mjs (names, taglines, features).
 *   2. src/content/plan-names.json, the plan names in app/core/billing_catalog.py
 *      (src/tests/planNames.test.ts keeps them in sync). Names only.
 *
 * Refresh the snapshot when prices or limits change: from frontend/, run
 *   node scripts/seo/snapshot_plans.mjs && node scripts/seo/lastmod.mjs
 * and commit both JSON files; node scripts/seo/check_plans_snapshot.mjs
 * reports drift from the live catalog.
 *
 * Prices render in the static HTML (founders, 2026-10-14: keep prices, with an
 * "online checkout opens soon" note while Stripe checkout is not live). No
 * offers go in the JSON-LD until checkout is live.
 */

import fs from "node:fs";
import path from "node:path";

import planNames from "@/content/plan-names.json";
import { featureList, formatPrice, type Catalog } from "@/lib/pricing";

export interface StaticPlan {
  name: string;
  /** "$149/mo", "$179 per booked meeting"; absent without a snapshot. */
  price?: string;
  tagline?: string;
  features: string[];
}

export interface StaticPlans {
  monthly: StaticPlan[];
  payPerMeeting: StaticPlan;
  trialDays?: number;
}

const SNAPSHOT = path.join(process.cwd(), "src", "content", "plans-snapshot.json");

function readSnapshot(): Catalog | null {
  if (!fs.existsSync(SNAPSHOT)) return null;
  return (JSON.parse(fs.readFileSync(SNAPSHOT, "utf8")) as { catalog: Catalog }).catalog;
}

export function staticPlans(): StaticPlans {
  const catalog = readSnapshot();
  if (!catalog) {
    return {
      monthly: planNames.monthly_tiers.map((name) => ({ name, features: [] })),
      payPerMeeting: { name: planNames.pay_per_meeting, features: [] },
    };
  }
  return {
    monthly: catalog.monthly.tiers.map((t) => ({
      name: t.name,
      price: `${formatPrice(t.price_cents, catalog.currency)}/mo`,
      tagline: t.tagline,
      features: featureList(t.limits),
    })),
    payPerMeeting: {
      name: catalog.pay_per_meeting.name,
      price:
        `${formatPrice(catalog.pay_per_meeting.price_per_meeting_cents, catalog.currency)} per booked meeting, ` +
        `${formatPrice(catalog.pay_per_meeting.monthly_fee_cents, catalog.currency)} monthly fee`,
      tagline: catalog.pay_per_meeting.tagline,
      features: featureList(catalog.pay_per_meeting.limits),
    },
    trialDays: catalog.trial_days,
  };
}
