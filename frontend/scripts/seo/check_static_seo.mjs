#!/usr/bin/env node
// Static SEO / AI-crawler readiness check for the marketing site.
//
// Reads the static export (frontend/out by default) and its sitemap.xml and
// robots.txt, and exits non-zero when any sitemap URL fails a check. It never
// makes a network request.
//
//   node scripts/seo/check_static_seo.mjs            # from frontend/, after `npm run build`
//   node scripts/seo/check_static_seo.mjs --out out --report   # also print a per-URL table
//   npm run build   # runs it as the postbuild hook (--postbuild: website builds only)
//
// Spec: docs/program/ai-visibility/SPEC.md (items 1.2, 2.3, 2.8, 2.9).
// Checks may be added; never remove or weaken one.

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(HERE, '..', '..');

const CANONICAL_HOST = 'www.calendarharvest.com';
const CRAWLERS = [
  'Googlebot',
  'Bingbot',
  'OAI-SearchBot',
  'Claude-SearchBot',
  'Claude-User',
  'PerplexityBot',
  'Meta-WebIndexer',
  'Google-Extended',
];
const SOFTWARE_APP_PATHS = new Set(['/', '/pricing/']);
const PRICING_PATH = '/pricing/';

const args = process.argv.slice(2);
const argValue = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const OUT = path.resolve(process.cwd(), argValue('--out') ?? path.join(FRONTEND, 'out'));
const REPORT = args.includes('--report');

// 2.3: the one source of product facts.
const FACTS_FILE = path.join(FRONTEND, 'src', 'content', 'product-facts.json');
const FACTS = JSON.parse(fs.readFileSync(FACTS_FILE, 'utf8'));
// Same rule as src/lib/productFacts.ts: the product name alone (VIC-NAME dropped "by Calendarharvest").
const PRODUCT_FULL_NAME = FACTS.brand.product_name;
// Legal pages whose title is legal text (see the title rule below).
const LEGAL_PAGES = new Set(['/privacy/', '/terms/']);
const SNAPSHOT_FILE = path.join(FRONTEND, 'src', 'content', 'plans-snapshot.json');

const failures = [];
const fail = (where, msg) => failures.push(`${where}: ${msg}`);

// ---------- robots.txt ----------

function parseRobots(text) {
  // Returns [{agents: [...lowercase], rules: [{allow, path}]}], plus sitemaps.
  const groups = [];
  const sitemaps = [];
  let current = null;
  let lastWasAgent = false;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/#.*/, '').trim();
    if (!line) continue;
    const idx = line.indexOf(':');
    if (idx < 0) continue;
    const key = line.slice(0, idx).trim().toLowerCase();
    const value = line.slice(idx + 1).trim();
    if (key === 'user-agent') {
      if (!current || !lastWasAgent) {
        current = { agents: [], rules: [] };
        groups.push(current);
      }
      current.agents.push(value.toLowerCase());
      lastWasAgent = true;
      continue;
    }
    lastWasAgent = false;
    if (key === 'sitemap') sitemaps.push(value);
    else if ((key === 'allow' || key === 'disallow') && current) {
      current.rules.push({ allow: key === 'allow', path: value });
    }
  }
  return { groups, sitemaps };
}

function ruleMatches(rulePath, urlPath) {
  if (rulePath === '') return false; // "Disallow:" with no value allows everything
  const anchored = rulePath.endsWith('$');
  const body = anchored ? rulePath.slice(0, -1) : rulePath;
  const re = new RegExp(
    '^' + body.split('*').map((s) => s.replace(/[.+?^${}()|[\]\\]/g, '\\$&')).join('.*') + (anchored ? '$' : ''),
  );
  return re.test(urlPath);
}

function isDisallowed(robots, agent, urlPath) {
  const token = agent.toLowerCase();
  let groups = robots.groups.filter((g) => g.agents.includes(token));
  if (groups.length === 0) groups = robots.groups.filter((g) => g.agents.includes('*'));
  const rules = groups.flatMap((g) => g.rules).filter((r) => ruleMatches(r.path, urlPath));
  if (rules.length === 0) return false;
  rules.sort((a, b) => b.path.length - a.path.length || Number(b.allow) - Number(a.allow));
  return !rules[0].allow;
}

// ---------- JSON-LD ----------

function collectNodes(value, out) {
  if (Array.isArray(value)) value.forEach((v) => collectNodes(v, out));
  else if (value && typeof value === 'object') {
    if (value['@type']) out.push(value);
    if (value['@graph']) collectNodes(value['@graph'], out);
  }
  return out;
}

function typesOf(node) {
  const t = node['@type'];
  return Array.isArray(t) ? t : [t];
}

function findKeyDeep(value, keys, trail = []) {
  if (Array.isArray(value)) {
    for (const v of value) {
      const hit = findKeyDeep(v, keys, trail);
      if (hit) return hit;
    }
  } else if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      if (keys.includes(k)) return [...trail, k].join('.');
      if (k === '@type' && typesOf(value).some((t) => keys.includes(String(t).charAt(0).toLowerCase() + String(t).slice(1)))) {
        return [...trail, `@type=${v}`].join('.');
      }
      const hit = findKeyDeep(v, keys, [...trail, k]);
      if (hit) return hit;
    }
  }
  return null;
}

// ---------- main ----------

function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return `(unparseable: ${url})`;
  }
}

function fileForPath(urlPath) {
  const rel = urlPath.replace(/^\/+/, '');
  return path.join(OUT, rel, 'index.html');
}

function main() {
  // As the npm postbuild hook, check website builds only. A mobile build
  // (NEXT_PUBLIC_BUILD_TARGET=mobile-dev|mobile-prod, the Android app) renders
  // no marketing markup on "/" by design (src/lib/homeEntry.ts) and is never
  // deployed as the website. Run directly, the check always runs.
  const target = process.env.NEXT_PUBLIC_BUILD_TARGET ?? 'web';
  if (args.includes('--postbuild') && target.startsWith('mobile')) {
    console.log(`check_static_seo: skipped for NEXT_PUBLIC_BUILD_TARGET=${target} (not the website build)`);
    return;
  }
  if (!fs.existsSync(OUT)) {
    console.error(`No export found at ${OUT}. Run \`npm run build\` first.`);
    process.exit(2);
  }

  const sitemapFile = path.join(OUT, 'sitemap.xml');
  const robotsFile = path.join(OUT, 'robots.txt');
  if (!fs.existsSync(sitemapFile)) fail('sitemap.xml', 'missing from the export');
  if (!fs.existsSync(robotsFile)) fail('robots.txt', 'missing from the export');
  const sitemapXml = fs.existsSync(sitemapFile) ? fs.readFileSync(sitemapFile, 'utf8') : '';
  const robots = parseRobots(fs.existsSync(robotsFile) ? fs.readFileSync(robotsFile, 'utf8') : '');

  if (robots.sitemaps.length === 0) fail('robots.txt', 'no Sitemap line');
  for (const s of robots.sitemaps) {
    if (hostOf(s) !== CANONICAL_HOST) fail('robots.txt', `Sitemap URL ${s} is not on ${CANONICAL_HOST}`);
  }

  const locs = [...sitemapXml.matchAll(/<loc>\s*([^<\s]+)\s*<\/loc>/g)].map((m) => m[1]);
  if (locs.length === 0) fail('sitemap.xml', 'no <loc> entries');

  const rows = [];
  for (const loc of locs) {
    const where = loc;
    if (hostOf(loc) !== CANONICAL_HOST) fail(where, `sitemap <loc> is not on ${CANONICAL_HOST}`);
    let urlPath;
    try {
      urlPath = new URL(loc).pathname;
    } catch {
      fail(where, 'sitemap <loc> does not parse as a URL');
      continue;
    }

    for (const agent of ['*', ...CRAWLERS]) {
      if (isDisallowed(robots, agent, urlPath)) fail(where, `disallowed in robots.txt for ${agent}`);
    }

    const file = fileForPath(urlPath);
    if (!fs.existsSync(file)) {
      fail(where, `in the sitemap but missing from the export (${path.relative(OUT, file)})`);
      rows.push({ path: urlPath, missing: true });
      continue;
    }
    const html = fs.readFileSync(file, 'utf8');
    const doc = new JSDOM(html).window.document;
    const meta = (sel) => doc.querySelector(sel)?.getAttribute('content')?.trim() ?? '';

    const title = doc.querySelector('head > title')?.textContent?.trim() ?? '';
    const description = meta('meta[name="description"]');
    const canonical = doc.querySelector('link[rel="canonical"]')?.getAttribute('href')?.trim() ?? '';
    const ogUrl = meta('meta[property="og:url"]');
    const h1 = doc.querySelector('h1')?.textContent?.replace(/\s+/g, ' ').trim() ?? '';

    if (!title) fail(where, 'no <title>');
    if (!description) fail(where, 'no meta description');
    if (!canonical) fail(where, 'no canonical link');
    if (!h1) fail(where, 'no <h1>');
    if (canonical && hostOf(canonical) !== CANONICAL_HOST) fail(where, `canonical ${canonical} is not on ${CANONICAL_HOST}`);
    if (canonical && canonical !== loc) fail(where, `canonical ${canonical} is not exactly its sitemap <loc>`);
    if (!ogUrl) fail(where, 'no og:url');
    if (ogUrl && hostOf(ogUrl) !== CANONICAL_HOST) fail(where, `og:url ${ogUrl} is not on ${CANONICAL_HOST}`);
    if (ogUrl && ogUrl !== loc) fail(where, `og:url ${ogUrl} is not exactly its sitemap <loc>`);

    for (const m of doc.querySelectorAll('meta[name="robots"], meta[name="googlebot"], meta[name="bingbot"]')) {
      if (/noindex/i.test(m.getAttribute('content') ?? '')) fail(where, `carries noindex (${m.outerHTML})`);
    }

    const nodes = [];
    for (const s of doc.querySelectorAll('script[type="application/ld+json"]')) {
      let parsed;
      try {
        parsed = JSON.parse(s.textContent);
      } catch (e) {
        fail(where, `JSON-LD does not parse: ${e.message}`);
        continue;
      }
      const ratingKey = findKeyDeep(parsed, ['aggregateRating', 'review', 'reviews']);
      if (ratingKey) fail(where, `JSON-LD contains rating/review markup (${ratingKey})`);
      collectNodes(parsed, nodes);
    }
    const types = new Set(nodes.flatMap(typesOf));
    for (const t of ['Organization', 'WebSite']) {
      if (!types.has(t)) fail(where, `no JSON-LD ${t}`);
    }
    if (SOFTWARE_APP_PATHS.has(urlPath) && !types.has('SoftwareApplication')) {
      fail(where, 'no JSON-LD SoftwareApplication');
    }

    if (html.includes('TODO')) fail(where, 'HTML contains the string TODO');

    // 2.3: titles carry the full product name built from the brand constant.
    // Terms and Privacy are legal text (Class C in docs/program/brand/rename-inventory.md):
    // their wording, title included, changes only with counsel, so they keep the
    // previous product name until the founders update them (founder-actions.md).
    if (title && !LEGAL_PAGES.has(urlPath) && !title.includes(PRODUCT_FULL_NAME)) {
      fail(where, `title lacks "${PRODUCT_FULL_NAME}"`);
    }
    checkFactsInJsonLd(where, nodes);

    const bodyText = (doc.querySelector('main') ?? doc.body)?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
    rows.push({
      path: urlPath,
      title,
      description,
      canonical,
      h1,
      words: bodyText ? bodyText.split(' ').length : 0,
      jsonld: [...types].join(', ') || '—',
      html,
      doc,
    });
  }

  // ---------- 2.9: lastmod from git for every sitemap URL ----------
  checkLastmod(sitemapXml);

  // ---------- 2.8: IndexNow key file ----------
  checkIndexNowKey();

  // ---------- pricing page: plan names ----------
  checkPlans(rows);

  if (REPORT) printReport(rows);

  if (failures.length) {
    console.log(`check_static_seo: FAIL (${failures.length})`);
    for (const f of failures) console.log(`  - ${f}`);
    process.exit(1);
  }
  console.log(`check_static_seo: PASS (${locs.length} sitemap URLs)`);
}

// 2.3: every sameAs and founder value in JSON-LD comes from the facts file,
// and every JSON-LD price from the 2.2 plans snapshot.
function stringLeaves(value, out = []) {
  if (typeof value === 'string' || typeof value === 'number') out.push(String(value));
  else if (Array.isArray(value)) value.forEach((v) => stringLeaves(v, out));
  else if (value && typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      if (k === '@type' || k === '@id' || k === '@context') continue;
      stringLeaves(v, out);
    }
  }
  return out;
}

function snapshotPrices() {
  if (!fs.existsSync(SNAPSHOT_FILE)) return new Set();
  const c = readJson(SNAPSHOT_FILE).catalog ?? {};
  const cents = [
    ...(c.monthly?.tiers ?? []).map((t) => t.price_cents),
    ...(c.annual?.tiers ?? []).map((t) => t.annual_price_cents),
    c.pay_per_meeting?.monthly_fee_cents,
    c.pay_per_meeting?.price_per_meeting_cents,
  ].filter((n) => typeof n === 'number');
  return new Set(cents.flatMap((n) => [String(n / 100), (n / 100).toFixed(2)]));
}

function checkFactsInJsonLd(where, nodes) {
  const allowedSameAs = new Set([...(FACTS.same_as ?? []), ...(FACTS.founders ?? []).flatMap((f) => f.same_as ?? [])]);
  const founderValues = new Set(stringLeaves(FACTS.founders ?? []));
  const prices = snapshotPrices();
  const visit = (value) => {
    if (Array.isArray(value)) return value.forEach(visit);
    if (!value || typeof value !== 'object') return;
    for (const s of [].concat(value.sameAs ?? [])) {
      if (!allowedSameAs.has(s)) fail(where, `JSON-LD sameAs ${s} is not in product-facts.json same_as`);
    }
    if (typesOf(value).includes('Person')) {
      for (const leaf of stringLeaves(value)) {
        if (!founderValues.has(leaf)) fail(where, `JSON-LD Person value "${leaf}" is not a founder fact in product-facts.json`);
      }
    }
    for (const key of ['price', 'lowPrice', 'highPrice']) {
      if (value[key] !== undefined && !prices.has(String(value[key]))) {
        fail(where, `JSON-LD ${key} ${value[key]} is not in plans-snapshot.json`);
      }
    }
    Object.values(value).forEach(visit);
  };
  visit(nodes);
}

function checkLastmod(sitemapXml) {
  const file = path.join(FRONTEND, 'src', 'content', 'sitemap-lastmod.json');
  const dates = fs.existsSync(file) ? readJson(file) : {};
  if (!fs.existsSync(file)) fail('sitemap-lastmod.json', 'missing; run node scripts/seo/lastmod.mjs');
  for (const m of sitemapXml.matchAll(/<url>([\s\S]*?)<\/url>/g)) {
    const loc = m[1].match(/<loc>\s*([^<\s]+)\s*<\/loc>/)?.[1];
    if (!loc) continue;
    let urlPath;
    try {
      urlPath = new URL(loc).pathname;
    } catch {
      continue;
    }
    if (!dates[urlPath]) fail(loc, 'no entry in sitemap-lastmod.json (run node scripts/seo/lastmod.mjs)');
    const lm = m[1].match(/<lastmod>\s*([^<\s]+)\s*<\/lastmod>/)?.[1];
    if (!lm) fail(loc, 'sitemap entry has no <lastmod>');
    else if (dates[urlPath] && lm !== dates[urlPath]) fail(loc, `sitemap <lastmod> ${lm} is not the git date ${dates[urlPath]}`);
  }
}

function checkIndexNowKey() {
  const { key } = readJson(path.join(HERE, 'indexnow.json'));
  const keyFile = path.join(OUT, `${key}.txt`);
  if (!fs.existsSync(keyFile)) fail('IndexNow', `key file ${key}.txt missing from the export`);
  else if (fs.readFileSync(keyFile, 'utf8').trim() !== key) fail('IndexNow', `${key}.txt does not contain the key`);
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function checkPlans(rows) {
  const expectedFile = path.join(HERE, 'expected_plans.json');
  const expected = fs.existsSync(expectedFile) ? readJson(expectedFile) : null;
  const names = expected?.plan_names ?? [];
  if (names.length === 0) {
    fail(PRICING_PATH, 'PLAN CHECK BLOCKED: no confirmed plan names');
    return;
  }
  const pricing = rows.find((r) => r.path === PRICING_PATH);
  if (!pricing || pricing.missing) {
    fail(PRICING_PATH, 'pricing page not in the export, cannot check plan names');
    return;
  }
  // Visible text only: <script> bodies (JSON-LD, the inline Next.js data)
  // must not satisfy the check when the rendered HTML lacks a plan.
  const body = pricing.doc.body.cloneNode(true);
  for (const el of body.querySelectorAll('script, style, noscript, template')) el.remove();
  const text = body.textContent.replace(/\s+/g, ' ');
  // 2.2: once committed, the plans snapshot (a copy of the live catalog) is
  // the source of plan names; it must still carry every expected name.
  const snapshotFile = path.join(FRONTEND, 'src', 'content', 'plans-snapshot.json');
  if (fs.existsSync(snapshotFile)) {
    const catalog = readJson(snapshotFile).catalog;
    const snapNames = [...(catalog?.monthly?.tiers ?? []).map((t) => t.name), catalog?.pay_per_meeting?.name].filter(Boolean);
    const removed = new Set(expected.removed_by_founders ?? []);
    for (const name of names) {
      if (!removed.has(name) && !snapNames.includes(name)) {
        fail(PRICING_PATH, `plan name "${name}" is missing from plans-snapshot.json (not in removed_by_founders)`);
      }
    }
    for (const name of snapNames) {
      if (!text.includes(name)) fail(PRICING_PATH, `snapshot plan name "${name}" not in the static HTML`);
    }
  }
  for (const name of names) {
    if (!text.includes(name)) fail(PRICING_PATH, `plan name "${name}" not in the static HTML`);
  }
  // 2026-10-15: prices shown in the static HTML before checkout is live
  // (founder decision): every snapshot price must be on the page.
  if (expected.prices_approved && expected.prices_in_html) {
    if (!fs.existsSync(snapshotFile)) {
      fail(PRICING_PATH, 'prices_in_html is set but plans-snapshot.json is missing');
    } else {
      const c = readJson(snapshotFile).catalog;
      const usd = (cents) => '$' + (cents / 100).toLocaleString('en-US');
      const cents = [...c.monthly.tiers.map((t) => t.price_cents), c.pay_per_meeting.price_per_meeting_cents];
      for (const n of cents) {
        if (!text.includes(usd(n))) fail(PRICING_PATH, `snapshot price "${usd(n)}" not in the static HTML`);
      }
    }
  }
  if (expected.prices_approved && expected.checkout_live) {
    for (const price of expected.prices ?? []) {
      if (!text.includes(price)) fail(PRICING_PATH, `approved price "${price}" not in the static HTML`);
    }
  }
}

function printReport(rows) {
  const cell = (s) => String(s ?? '').replace(/\|/g, '\\|').slice(0, 90);
  console.log('| Path | Title | Meta description | Canonical | H1 | Words in raw HTML main | JSON-LD types |');
  console.log('|---|---|---|---|---|---|---|');
  for (const r of rows) {
    if (r.missing) {
      console.log(`| ${r.path} | MISSING FROM EXPORT | | | | | |`);
      continue;
    }
    console.log(
      `| ${r.path} | ${cell(r.title) || '—'} | ${cell(r.description) || '—'} | ${cell(r.canonical) || '—'} | ${cell(r.h1) || '—'} | ${r.words} | ${cell(r.jsonld)} |`,
    );
  }
  console.log('');
}

main();
