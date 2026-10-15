#!/usr/bin/env node
// Tell IndexNow (Bing, and the other engines that share it; Copilot answers
// come from Bing) which sitemap URLs changed since the last submission.
//
// Run by a founder AFTER a production deploy, never by the build:
//   cd frontend && node scripts/seo/indexnow_submit.mjs
// Options:
//   --sitemap <path-or-url>  default: the deployed https://www.calendarharvest.com/sitemap.xml
//   --dry-run                print the exact JSON payload; send nothing; keep the state file
//
// A URL is submitted when its <lastmod> differs from the one recorded at the
// last successful submission, kept per URL in scripts/seo/.indexnow-state.json
// (gitignored; local to the machine that submits).

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CONFIG = JSON.parse(fs.readFileSync(path.join(HERE, 'indexnow.json'), 'utf8'));
const STATE_FILE = path.join(HERE, '.indexnow-state.json');
const ENDPOINT = 'https://api.indexnow.org/indexnow';
const DEFAULT_SITEMAP = `https://${CONFIG.host}/sitemap.xml`;

const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
// Refuse anything unknown, so a typo such as --dry-runb never sends for real.
const KNOWN = new Set(['--dry-run', '--sitemap']);
const unknown = args.filter((a, idx) => a.startsWith('--') && !KNOWN.has(a) && args[idx - 1] !== '--sitemap');
if (unknown.length) {
  console.error(`indexnow_submit: unknown option ${unknown.join(' ')}`);
  console.error('usage: node scripts/seo/indexnow_submit.mjs [--sitemap <path-or-url>] [--dry-run]');
  process.exit(2);
}
const i = args.indexOf('--sitemap');
const sitemapSource = i >= 0 ? args[i + 1] : DEFAULT_SITEMAP;
if (i >= 0 && (!sitemapSource || sitemapSource.startsWith('--'))) {
  console.error('usage: node scripts/seo/indexnow_submit.mjs [--sitemap <path-or-url>] [--dry-run]');
  process.exit(2);
}

async function readSitemap(source) {
  if (/^https?:\/\//.test(source)) {
    const res = await fetch(source);
    if (!res.ok) throw new Error(`GET ${source} returned HTTP ${res.status}`);
    return res.text();
  }
  return fs.readFileSync(source, 'utf8');
}

function entries(xml) {
  return [...xml.matchAll(/<url>([\s\S]*?)<\/url>/g)].map((m) => ({
    loc: m[1].match(/<loc>\s*([^<\s]+)\s*<\/loc>/)?.[1],
    lastmod: m[1].match(/<lastmod>\s*([^<\s]+)\s*<\/lastmod>/)?.[1] ?? '',
  })).filter((e) => e.loc);
}

function readState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
  } catch {
    return {};
  }
}

async function main() {
  const all = entries(await readSitemap(sitemapSource));
  const offHost = all.filter((e) => new URL(e.loc).host !== CONFIG.host);
  if (offHost.length) throw new Error(`sitemap URLs not on ${CONFIG.host}: ${offHost.map((e) => e.loc).join(', ')}`);
  const state = readState();
  const changed = all.filter((e) => state[e.loc] !== e.lastmod);
  const payload = {
    host: CONFIG.host,
    key: CONFIG.key,
    keyLocation: `https://${CONFIG.host}/${CONFIG.key}.txt`,
    urlList: changed.map((e) => e.loc),
  };
  if (dryRun) {
    console.log(`indexnow_submit --dry-run: ${changed.length} of ${all.length} URLs changed since the last submission (${sitemapSource}).`);
    console.log(`Would POST to ${ENDPOINT}:`);
    console.log(JSON.stringify(payload, null, 2));
    return;
  }
  if (changed.length === 0) {
    console.log('indexnow_submit: nothing changed since the last submission.');
    return;
  }
  const res = await fetch(ENDPOINT, {
    method: 'POST',
    headers: { 'content-type': 'application/json; charset=utf-8' },
    body: JSON.stringify(payload),
  });
  if (res.status !== 200 && res.status !== 202) {
    throw new Error(`IndexNow returned HTTP ${res.status}: ${await res.text()}`);
  }
  for (const e of changed) state[e.loc] = e.lastmod;
  fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2) + '\n');
  console.log(`indexnow_submit: submitted ${changed.length} URLs (HTTP ${res.status}).`);
}

main().catch((e) => {
  console.error(`indexnow_submit: ${e.message}`);
  process.exit(1);
});
