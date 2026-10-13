/**
 * Canonical URL and og:url for the public marketing pages.
 *
 * One host (www) and one trailing-slash form (next.config.js trailingSlash:
 * true), so each page's canonical is exactly its <loc> in /sitemap.xml.
 * scripts/seo/check_static_seo.mjs fails the build output if they drift.
 */

import type { Metadata } from "next";

import sitePages from "@/content/site-pages.json";

export const SITE_ORIGIN = sitePages.origin;

export type SitePath = (typeof sitePages.pages)[number]["path"];

export function absoluteUrl(path: string): string {
  return `${SITE_ORIGIN}${path}`;
}

/** Metadata fields that pin a page to its canonical URL. */
export function canonicalMeta(
  path: SitePath,
  openGraph: Metadata["openGraph"] = {},
): Pick<Metadata, "alternates" | "openGraph"> {
  const url = absoluteUrl(path);
  return { alternates: { canonical: url }, openGraph: { ...openGraph, url } };
}
