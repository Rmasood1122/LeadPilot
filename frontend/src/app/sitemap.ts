/**
 * /sitemap.xml, generated at build time from src/content/site-pages.json so
 * the sitemap, the canonical tags and robots.txt share one host. lastmod is
 * each page's last real content change, written from git by
 * scripts/seo/lastmod.mjs into src/content/sitemap-lastmod.json (the build
 * never reads git, and never uses the build time).
 */

import type { MetadataRoute } from "next";

import sitePages from "@/content/site-pages.json";
import lastmod from "@/content/sitemap-lastmod.json";
import { absoluteUrl } from "@/lib/seo/pageMeta";

export const dynamic = "force-static";

type ChangeFrequency = NonNullable<MetadataRoute.Sitemap[number]["changeFrequency"]>;

export default function sitemap(): MetadataRoute.Sitemap {
  return sitePages.pages.map((page) => ({
    url: absoluteUrl(page.path),
    lastModified: (lastmod as Record<string, string>)[page.path],
    changeFrequency: page.changefreq as ChangeFrequency,
    priority: page.priority,
  }));
}
