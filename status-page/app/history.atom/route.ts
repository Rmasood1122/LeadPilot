import { siteUrl } from "../../lib/config.ts";
import { buildAtom } from "../../lib/feeds.ts";
import { incidentsDir, loadIncidents } from "../../lib/incidents.ts";

// Built at deploy time; incidents only change by deploy.
export const dynamic = "force-static";

export function GET(): Response {
  const now = new Date();
  return new Response(buildAtom(loadIncidents(incidentsDir(), now), siteUrl(), now), {
    headers: { "Content-Type": "application/atom+xml; charset=utf-8" },
  });
}
