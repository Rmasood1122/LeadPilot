/**
 * app/help/[slug]/page.tsx — /help/<article id>/: one static page per
 * help-center article (dynamicParams = false).
 */

import type { Metadata } from "next";

import { ContentPage } from "@/components/content/ContentPage";
import { plainText } from "@/lib/content/richText";
import { helpArticle, helpArticles, helpStatusNote } from "@/lib/content/helpCenter";
import { canonicalMeta } from "@/lib/seo/pageMeta";
import { pageGraph } from "@/lib/seo/structuredData";

export const dynamicParams = false;

export function generateStaticParams() {
  return helpArticles().map((a) => ({ slug: a.id }));
}

const pathOf = (id: string) => `/help/${id}/`;

function describe(text: string): string {
  const plain = plainText(text);
  return plain.length <= 155 ? plain : `${plain.slice(0, 152).replace(/\s+\S*$/, "")}…`;
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const a = helpArticle(params.slug);
  return {
    title: `${a.title} | Victorae help | Calendarharvest`,
    description: describe(a.lead[0] ?? a.title),
    ...canonicalMeta(pathOf(a.id)),
  };
}

export default function HelpArticlePage({ params }: { params: { slug: string } }) {
  const a = helpArticle(params.slug);
  return (
    <ContentPage
      jsonLd={pageGraph({ path: pathOf(a.id), breadcrumb: a.title })}
      current="/help"
      eyebrow="Help center"
      h1={a.title}
      lead={a.lead}
      disclosure={helpStatusNote()}
      lastChecked={a.lastVerified || undefined}
      sections={a.sections}
      related={[{ href: "/help", label: "All help articles" }, { href: "/faq", label: "Victorae FAQ" }]}
    />
  );
}
