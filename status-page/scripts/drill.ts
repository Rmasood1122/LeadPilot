/**
 * npm run drill [-- --incidents <dir>] [-- --feeds]
 *
 * Runs the status page's data layer once with the current environment
 * (UPTIMEROBOT_API_KEY, UPTIMEROBOT_API_URL, LEADPILOT_API_URL) and prints
 * what the home page would show. Used for the exit-gate-3 drills in
 * docs/program/STATUS_PAGE.md. Never prints the API key.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { readEnv, siteUrl } from "../lib/config.ts";
import { buildAtom, buildRss } from "../lib/feeds.ts";
import { loadIncidents, recentIncidents } from "../lib/incidents.ts";
import { getSnapshot } from "../lib/snapshot.ts";
import { STATUS_LABELS } from "../lib/status.ts";

const args = process.argv.slice(2);
const here = path.dirname(fileURLToPath(import.meta.url));
const dirArg = args.indexOf("--incidents");
const dir = dirArg >= 0 ? path.resolve(args[dirArg + 1]!) : path.join(here, "..", "incidents");

const now = new Date();
const incidents = loadIncidents(dir, now);
const snap = await getSnapshot(readEnv(), { fetch, now, incidents });

console.log(`generated_at   ${snap.generatedAt}`);
console.log(`sources        uptimerobot=${snap.sources.uptimeRobot} backend=${snap.sources.backend}`);
if (snap.dataNotice) console.log(`DATA NOTICE    ${snap.dataNotice.title}: ${snap.dataNotice.text}`);
console.log(`BANNER         ${snap.overall.title}`);
for (const c of snap.components) {
  const bars = c.uptime ? `${c.uptime.days.filter((d) => d.uptime !== null).length}/90 days with data` : "no bars";
  console.log(
    `  ${c.name.padEnd(22)} ${STATUS_LABELS[c.status].padEnd(21)} source=${c.source.padEnd(8)} ${c.note ?? ""}${c.checkedAt ? ` checked ${c.checkedAt}` : ""} [${bars}]`,
  );
}
const recent = recentIncidents(incidents, now, 14);
console.log(`incidents      ${incidents.length} total, ${recent.length} shown on home page`);
for (const i of recent) console.log(`  - ${i.slug}: ${i.title} (${i.resolved ? "resolved" : i.updates[0]!.status})`);
if (args.includes("--feeds")) {
  console.log("\n--- /history.rss ---\n" + buildRss(incidents, siteUrl(), now));
  console.log("--- /history.atom ---\n" + buildAtom(incidents, siteUrl(), now));
}
