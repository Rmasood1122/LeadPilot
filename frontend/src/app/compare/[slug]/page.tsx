/**
 * app/compare/[slug]/page.tsx — /compare/leadpilot-vs-<competitor>/.
 * One static page per entry in src/content/geo/compare.ts (no other slug is
 * built: dynamicParams = false).
 */

import type { Metadata } from "next";

import { ContentPage } from "@/components/content/ContentPage";
import { COMPARISONS, comparison, comparisonPath, comparisonSections } from "@/content/geo/compare";
import { COMPETITORS_CHECKED, FOUNDER_DISCLOSURE } from "@/content/geo/shared";
import { canonicalMeta } from "@/lib/seo/pageMeta";
import { pageGraph } from "@/lib/seo/structuredData";

export const dynamicParams = false;

const PREFIX = "leadpilot-vs-";

export function generateStaticParams() {
  return COMPARISONS.map((c) => ({ slug: `${PREFIX}${c.slug}` }));
}

function load(slug: string) {
  return comparison(slug.slice(PREFIX.length));
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const c = load(params.slug);
  return { title: c.title, description: c.description, ...canonicalMeta(comparisonPath(c.slug)) };
}

export default function ComparisonPage({ params }: { params: { slug: string } }) {
  const c = load(params.slug);
  const others = COMPARISONS.filter((o) => o.slug !== c.slug);
  return (
    <ContentPage
      jsonLd={pageGraph({ path: comparisonPath(c.slug), breadcrumb: `Victorae vs ${c.competitor}` })}
      current="/compare"
      eyebrow="Compare"
      h1={c.h1}
      lead={[`**Short answer:** ${c.shortAnswer}`]}
      disclosure={FOUNDER_DISCLOSURE}
      lastChecked={COMPETITORS_CHECKED}
      sections={comparisonSections(c)}
      related={[
        ...others.map((o) => ({ href: comparisonPath(o.slug).slice(0, -1), label: `Victorae vs ${o.competitor}` })),
        { href: "/compare", label: "All comparisons" },
        { href: "/pricing", label: "Victorae pricing" },
      ]}
    />
  );
}
