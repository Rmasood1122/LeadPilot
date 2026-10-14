#!/usr/bin/env node
// Write each sitemap URL's lastmod from git, so the sitemap carries real change
// dates and the build never reads git or uses the build time.
//
//   cd frontend && node scripts/seo/lastmod.mjs
//
// For each page in src/content/site-pages.json, the date is the latest commit
// (`git log -1 --format=%cI -- <files>`) touching that page's `sources`: its
// own files, the plans snapshot for /pricing, and product-facts.json only where
// the page body renders it (never shared layout/header/footer files).
// Writes src/content/sitemap-lastmod.json. Run it after any page change, and
// commit its JSON separately on the same branch before merge.

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, '..', '..');
const PAGES = JSON.parse(fs.readFileSync(path.join(FRONTEND, 'src', 'content', 'site-pages.json'), 'utf8')).pages;
const OUT = path.join(FRONTEND, 'src', 'content', 'sitemap-lastmod.json');

const git = (...args) => execFileSync('git', args, { cwd: FRONTEND, encoding: 'utf8' }).trim();

if (git('rev-parse', '--is-shallow-repository') === 'true') {
  console.error('lastmod: this clone is shallow, so dates would be wrong. Run `git fetch --unshallow` first.');
  process.exit(1);
}
const dirty = git('status', '--porcelain', '--', ...PAGES.flatMap((p) => p.sources).filter((f) => fs.existsSync(path.join(FRONTEND, f))));
if (dirty) {
  console.error(`lastmod: commit these page sources first, so their dates exist in git:\n${dirty}`);
  process.exit(1);
}

const out = {};
for (const page of PAGES) {
  const date = git('log', '-1', '--format=%cI', '--', ...page.sources);
  if (!date) {
    console.error(`lastmod: no commit found for ${page.path} (${page.sources.join(', ')})`);
    process.exit(1);
  }
  // One format on every OS and git version (some print +00:00, some Z).
  out[page.path] = new Date(date).toISOString().replace(/\.\d{3}Z$/, 'Z');
}
fs.writeFileSync(OUT, JSON.stringify(out, null, 2) + '\n');
console.log(`Wrote ${path.relative(process.cwd(), OUT)}:`);
for (const [p, d] of Object.entries(out)) console.log(`  ${p}  ${d}`);
