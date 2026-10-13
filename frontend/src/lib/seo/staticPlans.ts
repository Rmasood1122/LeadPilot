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
 * TODO(founder): no snapshot exists yet; the live API could not be reached from
 * the session that wrote this. From frontend/, run
 *   node scripts/seo/snapshot_plans.mjs && node scripts/seo/lastmod.mjs
 * and commit both JSON files, so plan features also render statically.
 *
 * TODO(founder): prices are deliberately NOT rendered here, and no offers go in
 * the JSON-LD, because Stripe checkout is not live (Phase 0, 2026-10-13). Decide
 * whether showing prices before checkout is live implies an offer buyers can
 * purchase; then set checkout_live in scripts/seo/expected_plans.json.
 */

import fs from "node:fs";
import path from "node:path";

import planNames from "@/content/plan-names.json";
import { featureList, type Catalog } from "@/lib/pricing";

export interface StaticPlan {
  name: string;
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
    monthly: catalog.monthly.tiers.map((t) => ({ name: t.name, tagline: t.tagline, features: featureList(t.limits) })),
    payPerMeeting: {
      name: catalog.pay_per_meeting.name,
      tagline: catalog.pay_per_meeting.tagline,
      features: featureList(catalog.pay_per_meeting.limits),
    },
    trialDays: catalog.trial_days,
  };
}
