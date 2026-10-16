/**
 * app/for/[slug]/page.tsx — /for/agencies/, /for/b2b-service-firms/,
 * /for/local-businesses/ (src/content/geo/forPages.ts).
 */

import type { Metadata } from "next";

import { ContentPage } from "@/components/content/ContentPage";
import { FOR_PAGES, forPage } from "@/content/geo/forPages";
import { FACTS_CHECKED } from "@/content/geo/shared";
import { canonicalMeta } from "@/lib/seo/pageMeta";
import { pageGraph } from "@/lib/seo/structuredData";

export const dynamicParams = false;

export function generateStaticParams() {
  return FOR_PAGES.map((p) => ({ slug: p.slug }));
}

const pathOf = (slug: string) => `/for/${slug}/`;

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const p = forPage(params.slug);
  return { title: p.title, description: p.description, ...canonicalMeta(pathOf(p.slug)) };
}

export default function ForPage({ params }: { params: { slug: string } }) {
  const p = forPage(params.slug);
  return (
    <ContentPage
      jsonLd={pageGraph({ path: pathOf(p.slug), breadcrumb: p.eyebrow })}
      eyebrow={p.eyebrow}
      h1={p.h1}
      lead={p.lead}
      lastChecked={FACTS_CHECKED}
      sections={p.sections}
      related={p.related}
    />
  );
}
