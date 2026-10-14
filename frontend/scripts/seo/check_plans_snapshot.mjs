#!/usr/bin/env node
// Founder-run check (not part of the build): does the committed plans
// snapshot still match the live GET /billing/catalog?
//
//   cd frontend && node scripts/seo/check_plans_snapshot.mjs [--api https://<api-origin>]
//
// Exit 0: identical. Exit 1: drift (re-run snapshot_plans.mjs and commit) or
// no snapshot. Exit 2: the live catalog could not be fetched.

import fs from 'node:fs';
import { isDeepStrictEqual } from 'node:util';

import { SNAPSHOT_FILE, apiOrigin, fetchCatalog } from './snapshot_plans.mjs';

if (!fs.existsSync(SNAPSHOT_FILE)) {
  console.log('check_plans_snapshot: no snapshot committed yet. Run: node scripts/seo/snapshot_plans.mjs');
  process.exit(1);
}
const snapshot = JSON.parse(fs.readFileSync(SNAPSHOT_FILE, 'utf8'));
let live;
try {
  live = await fetchCatalog(apiOrigin());
} catch (e) {
  console.log(`check_plans_snapshot: could not fetch the live catalog: ${e.message}`);
  process.exit(2);
}
if (isDeepStrictEqual(snapshot.catalog, live.catalog)) {
  console.log(`check_plans_snapshot: OK, snapshot from ${snapshot.fetched_at} matches ${live.url}`);
  process.exit(0);
}
console.log(`check_plans_snapshot: DRIFT, snapshot from ${snapshot.fetched_at} differs from ${live.url}.`);
console.log('Re-run node scripts/seo/snapshot_plans.mjs, review the diff, and commit it.');
process.exit(1);
