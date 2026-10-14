#!/usr/bin/env node
// Snapshot the live plan catalog into a committed JSON file that the pricing
// page renders as static HTML (plan names, taglines and features), so crawlers
// that do not run JavaScript can read the plans.
//
// The catalog's only source is the backend: GET /billing/catalog, which reads
// app/core/billing_catalog.py and app/core/plans.py. This script never invents
// values; it copies what the live endpoint returns. It is NOT part of the
// build (the build must not call the backend).
//
//   cd frontend
//   node scripts/seo/snapshot_plans.mjs                 # default API origin below
//   node scripts/seo/snapshot_plans.mjs --api https://<api-origin>
//
// Then commit src/content/plans-snapshot.json, run the lastmod script
// (scripts/seo/lastmod.mjs) and commit its JSON too.
// Later, check for drift with: node scripts/seo/check_plans_snapshot.mjs

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const SNAPSHOT_FILE = path.resolve(HERE, '..', '..', 'src', 'content', 'plans-snapshot.json');
// Production API origin per DEPLOY_RENDER_FREE.md (Vercel NEXT_PUBLIC_API_URL).
export const DEFAULT_API = 'https://leadpilot-api-ph3t.onrender.com';

export function apiOrigin(argv = process.argv.slice(2)) {
  const i = argv.indexOf('--api');
  return (i >= 0 ? argv[i + 1] : process.env.NEXT_PUBLIC_API_URL || DEFAULT_API).replace(/\/+$/, '');
}

export async function fetchCatalog(origin) {
  const url = `${origin}/billing/catalog`;
  const res = await fetch(url, { headers: { accept: 'application/json' } });
  if (!res.ok) throw new Error(`GET ${url} returned HTTP ${res.status}`);
  return { url, catalog: await res.json() };
}

async function main() {
  const { url, catalog } = await fetchCatalog(apiOrigin());
  if (!catalog?.monthly?.tiers?.length || !catalog?.pay_per_meeting?.name) {
    throw new Error(`${url} did not return a plan catalog`);
  }
  const snapshot = { source_url: url, fetched_at: new Date().toISOString(), catalog };
  fs.writeFileSync(SNAPSHOT_FILE, JSON.stringify(snapshot, null, 2) + '\n');
  const names = [...catalog.monthly.tiers.map((t) => t.name), catalog.pay_per_meeting.name];
  console.log(`Wrote ${path.relative(process.cwd(), SNAPSHOT_FILE)} from ${url}: ${names.join(', ')}`);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => {
    console.error(`snapshot_plans: ${e.message}`);
    process.exit(1);
  });
}
