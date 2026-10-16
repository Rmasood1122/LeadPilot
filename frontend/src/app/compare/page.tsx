/**
 * app/compare/page.tsx — /compare/: every comparison page, plus the "who each
 * tool is best for" summary (src/content/geo/compare.ts).
 */

import type { Metadata } from "next";

import { ContentPage } from "@/components/content/ContentPage";
import { COMPARISONS, comparisonPath } from "@/content/geo/compare";
import { COMPETITORS_CHECKED, FOUNDER_DISCLOSURE } from "@/content/geo/shared";
import { canonicalMeta } from "@/lib/seo/pageMeta";
import { pageGraph } from "@/lib/seo/structuredData";

export const metadata: Metadata = {
  title: "LeadPilot by Calendarharvest compared: Apollo, Instantly, Smartlead, Clay, Artisan | Calendarharvest",
  description:
    "How LeadPilot by Calendarharvest compares with Apollo.io, Instantly, Smartlead, Clay and Artisan, and with hiring an SDR: who each tool is best for, written by LeadPilot's founders.",
  ...canonicalMeta("/compare/"),
};

export default function CompareHubPage() {
  return (
    <ContentPage
      jsonLd={pageGraph({ path: "/compare/", breadcrumb: "Compare" })}
      current="/compare"
      eyebrow="Compare"
      h1="LeadPilot compared with the tools buyers weigh it against"
      lead={[
        "LeadPilot by Calendarharvest is built for founder-led agencies and B2B service firms that want the research, contacts and one-to-one emails done for them and approve sending daily. Other tools are better at other jobs; each comparison says when to choose them instead.",
      ]}
      disclosure={FOUNDER_DISCLOSURE}
      lastChecked={COMPETITORS_CHECKED}
      sections={[
        {
          heading: "Who each tool is best for",
          blocks: [
            {
              kind: "table",
              head: ["Tool", "Best for", "Comparison"],
              rows: [
                ["LeadPilot", "Founder-led agencies and B2B service firms (5 to 50 people) with no sales team who want research, contacts and one-to-one emails done for them, and approve sending daily", "—"],
                ...COMPARISONS.map((c) => [c.competitor, c.bestFor, `[LeadPilot vs ${c.competitor}](${comparisonPath(c.slug)})`]),
              ],
            },
          ],
        },
      ]}
      related={[
        { href: "/what-is-leadpilot", label: "What is LeadPilot?" },
        { href: "/faq", label: "LeadPilot FAQ" },
      ]}
    />
  );
}
