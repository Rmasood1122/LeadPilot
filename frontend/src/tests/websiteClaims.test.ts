import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

/** Founder decision D1 (2026-10-10, docs/program/DECISIONS.md): the public
 *  website describes what the code does. These phrases were on the site and
 *  were false: outreach is sent automatically (app/workers/outreach_tasks.py),
 *  not by human senders; the research pipeline runs per campaign strategy
 *  (app/pipeline/engine.py), not per prospect; and the brand is
 *  Calendarharvest (calendarharvest.com), not "Clanderharvest". If one of them
 *  comes back, this fails and names the file. */

const BANNED: { phrase: RegExp; why: string }[] = [
  { phrase: /clanderharvest/i, why: "typo of Calendarharvest" },
  { phrase: /not\s+bots/i, why: "outreach is sent automatically" },
  { phrase: /human\s+senders?/i, why: "outreach is sent automatically" },
  { phrase: /on\s+every\s+prospect/i, why: "research runs per campaign strategy" },
  // 2026-10-11 (docs/features/gdpr-erasure.md): no analytics code exists, and
  // account deletion is self-serve on the Profile page.
  { phrase: /provides\s+analytics/i, why: "no analytics provider is used" },
  { phrase: /to\s+ask\s+us\s+to\s+delete\s+your\s+account\s+or\s+any\s+other\s+data,\s+contact/i,
    why: "account deletion is self-serve (DELETE /me)" },
];

const ROOTS = ["src/app", "src/components"];

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) out.push(...sourceFiles(full));
    else if (/\.(tsx?|mdx?)$/.test(name)) out.push(full);
  }
  return out;
}

const PUBLIC_PAGES = [
  "src/app/how-it-works/page.tsx",
  "src/app/about/page.tsx",
  "src/app/terms/page.tsx",
  "src/app/privacy/page.tsx",
  "src/components/Footer.tsx",
];

describe("website copy matches the code (D1)", () => {
  const files = ROOTS.flatMap(sourceFiles);

  it("scans the public marketing and legal pages", () => {
    for (const page of PUBLIC_PAGES) expect(files).toContain(path.normalize(page));
  });

  for (const { phrase, why } of BANNED) {
    it(`no page says ${phrase} (${why})`, () => {
      const hits = files.filter((f) => phrase.test(readFileSync(f, "utf8")));
      expect(hits).toEqual([]);
    });
  }

  it("the brand is spelled Calendarharvest in titles and the footer", () => {
    expect(readFileSync("src/components/Footer.tsx", "utf8")).toContain("Calendarharvest");
    for (const page of PUBLIC_PAGES.filter((p) => p.endsWith("page.tsx"))) {
      expect(readFileSync(page, "utf8")).toMatch(/title: "[^"]*\| Calendarharvest"/);
    }
  });
});
