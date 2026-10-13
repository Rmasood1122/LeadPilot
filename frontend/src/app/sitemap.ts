/**
 * /sitemap.xml, generated at build time from src/content/site-pages.json so
 * the sitemap, the canonical tags and robots.txt share one host.
 */

import type { MetadataRoute } from "next";

import sitePages from "@/content/site-pages.json";
import { absoluteUrl } from "@/lib/seo/pageMeta";

export const dynamic = "force-static";

type ChangeFrequency = NonNullable<MetadataRoute.Sitemap[number]["changeFrequency"]>;

export default function sitemap(): MetadataRoute.Sitemap {
  return sitePages.pages.map((page) => ({
    url: absoluteUrl(page.path),
    lastModified: page.lastmod,
    changeFrequency: page.changefreq as ChangeFrequency,
    priority: page.priority,
  }));
}
