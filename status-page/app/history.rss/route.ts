import { siteUrl } from "../../lib/config.ts";
import { buildRss } from "../../lib/feeds.ts";
import { incidentsDir, loadIncidents } from "../../lib/incidents.ts";

// Built at deploy time; incidents only change by deploy.
export const dynamic = "force-static";

export function GET(): Response {
  const now = new Date();
  return new Response(buildRss(loadIncidents(incidentsDir(), now), siteUrl(), now), {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8" },
  });
}
