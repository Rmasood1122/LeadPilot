import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "node:test";

const ROOT = path.join(import.meta.dirname, "..");

function sources(dir: string): string[] {
  const out: string[] = [];
  for (const entry of fs.readdirSync(path.join(ROOT, dir), { withFileTypes: true })) {
    const rel = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sources(rel));
    else if (/\.(ts|tsx|mjs)$/.test(entry.name)) out.push(rel);
  }
  return out;
}

const ALL = [...sources("app"), ...sources("components"), ...sources("lib"), "next.config.mjs"];

describe("the UptimeRobot key cannot reach the browser", () => {
  it("no NEXT_PUBLIC_ variable is used anywhere (those are inlined into client bundles)", () => {
    for (const file of ALL) {
      assert.ok(!fs.readFileSync(path.join(ROOT, file), "utf8").includes("NEXT_PUBLIC_"), file);
    }
  });

  it("the key is named only in lib/config.ts (env) and lib/uptimerobot.ts (docs), never read from process.env there", () => {
    const readers = ALL.filter((f) => fs.readFileSync(path.join(ROOT, f), "utf8").includes("UPTIMEROBOT_API_KEY"));
    assert.deepEqual(readers.sort(), ["lib/config.ts", "lib/uptimerobot.ts"]);
    assert.ok(!fs.readFileSync(path.join(ROOT, "lib/uptimerobot.ts"), "utf8").includes("process.env"));
  });

  it("client components import no server-side data modules", () => {
    const serverOnly = ["config.ts", "uptimerobot.ts", "backend.ts", "snapshot.ts", "incidents.ts"];
    for (const file of ALL) {
      const src = fs.readFileSync(path.join(ROOT, file), "utf8");
      if (!/^["']use client["']/.test(src.trimStart())) continue;
      for (const mod of serverOnly) assert.ok(!src.includes(`lib/${mod}`), `${file} imports ${mod}`);
    }
  });
});

describe("the page revalidates every 60 s", () => {
  it("home page and /api/status export revalidate = 60 and match lib/config.ts", async () => {
    const { REVALIDATE_SECONDS } = await import("../lib/config.ts");
    assert.equal(REVALIDATE_SECONDS, 60);
    for (const file of ["app/page.tsx", "app/api/status/route.ts"]) {
      assert.match(fs.readFileSync(path.join(ROOT, file), "utf8"), /export const revalidate = 60;/, file);
    }
  });

  it("no fetch opts out of caching (that would call UptimeRobot on every view)", () => {
    for (const file of ALL) {
      const src = fs.readFileSync(path.join(ROOT, file), "utf8");
      assert.ok(!/cache:\s*["']no-store["']/.test(src), file);
      assert.ok(!/export const dynamic = ["']force-dynamic["']/.test(src), file);
    }
  });
});
