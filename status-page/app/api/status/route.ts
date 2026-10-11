import { readEnv } from "../../../lib/config.ts";
import { incidentsDir, loadIncidents } from "../../../lib/incidents.ts";
import { getSnapshot } from "../../../lib/snapshot.ts";

// The same snapshot the home page renders, as JSON (for scripts and the
// post-deploy smoke check). Server-side only; the UptimeRobot key is never in it.
export const revalidate = 60;

export async function GET(): Promise<Response> {
  const now = new Date();
  const snap = await getSnapshot(readEnv(), { fetch, now, incidents: loadIncidents(incidentsDir(), now) });
  return Response.json(snap);
}
