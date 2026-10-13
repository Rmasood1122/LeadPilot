/**
 * app/pricing/page.tsx: the public pricing page at /pricing.
 *
 * A server component so the page carries its own title, description and
 * canonical URL. The interactive page (plans loaded from GET /billing/catalog,
 * checkout) is PricingClient.
 */

import type { Metadata } from "next";

import { Footer } from "@/components/Footer";
import { canonicalMeta } from "@/lib/seo/pageMeta";

import { PricingClient } from "./PricingClient";

export const metadata: Metadata = {
  ...canonicalMeta("/pricing/"),
};

export default function PricingPage() {
  return <PricingClient footer={<Footer tone="theme" />} />;
}
