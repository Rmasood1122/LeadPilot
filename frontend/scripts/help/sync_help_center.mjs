#!/usr/bin/env node
/**
 * Copies the help-center articles (docs/help-center/NN-*.md) into
 * frontend/src/content/help-center/ so the /help/ pages build from files
 * inside frontend/ (Vercel's root directory). docs/help-center/ stays the
 * source of truth; src/tests/helpCenterCopy.test.ts fails when the copy drifts.
 *
 * Usage (from frontend/): node scripts/help/sync_help_center.mjs
 */
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve('..', 'docs', 'help-center');
const DEST = path.resolve('src', 'content', 'help-center');
const ARTICLE = /^\d\d-[a-z0-9-]+\.md$/;

fs.mkdirSync(DEST, { recursive: true });
for (const name of fs.readdirSync(DEST)) {
  if (ARTICLE.test(name) && !fs.existsSync(path.join(SRC, name))) fs.rmSync(path.join(DEST, name));
}
let n = 0;
for (const name of fs.readdirSync(SRC).sort()) {
  if (!ARTICLE.test(name) || name.startsWith('00-')) continue;
  fs.copyFileSync(path.join(SRC, name), path.join(DEST, name));
  n++;
}
console.log(`sync_help_center: copied ${n} articles to ${path.relative(process.cwd(), DEST)}`);
