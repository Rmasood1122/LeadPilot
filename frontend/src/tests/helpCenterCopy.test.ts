import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { parseArticle, rewriteLinks, slugify } from "@/lib/content/markdown";

/** /help/ is built from src/content/help-center/, a copy of docs/help-center/
 *  (the source of truth) made by scripts/help/sync_help_center.mjs. The copy
 *  must match byte for byte; rerun the script after editing an article. */

const SRC = path.resolve("..", "docs", "help-center");
const COPY = "src/content/help-center";
const ARTICLE = /^\d\d-[a-z0-9-]+\.md$/;

describe("help-center copy", () => {
  const source = readdirSync(SRC).filter((f) => ARTICLE.test(f) && !f.startsWith("00-")).sort();

  it("has exactly the source articles", () => {
    expect(readdirSync(COPY).filter((f) => ARTICLE.test(f)).sort()).toEqual(source);
  });

  for (const f of source) {
    it(`${f} matches docs/help-center (run node scripts/help/sync_help_center.mjs)`, () => {
      expect(readFileSync(path.join(COPY, f), "utf8")).toBe(readFileSync(path.join(SRC, f), "utf8"));
    });
  }
});

describe("help-center markdown parser", () => {
  const raw = [
    "---", "id: sample", "title: Sample", "audience: customer", "last_verified: 2026-10-10", "sources:", "  - app/x.py", "---", "",
    "# Sample article", "", "Intro line one", "continues here.", "",
    "## Do I approve sending every day?", "", "- one **bold**", "- two", "", "1. first", "2. second", "",
    "| A | B |", "|---|---|", "| x | y |", "", "### Sub", "", "See [other](02-other.md#a-heading) and [missing](99-x.md).",
  ].join("\n");
  const a = parseArticle(raw, { "02-other.md": "other" });

  it("reads front matter, title and lead", () => {
    expect(a.id).toBe("sample");
    expect(a.title).toBe("Sample article");
    expect(a.lastVerified).toBe("2026-10-10");
    expect(a.lead).toEqual(["Intro line one continues here."]);
  });

  it("builds sections with anchors, lists, tables and subheadings", () => {
    const s = a.sections[0];
    expect(s.id).toBe("do-i-approve-sending-every-day");
    expect(s.blocks.map((b) => b.kind)).toEqual(["ul", "ol", "table", "h3", "p"]);
    expect(s.blocks[2]).toEqual({ kind: "table", head: ["A", "B"], rows: [["x", "y"]] });
  });

  it("rewrites article links to /help/ pages and drops unknown ones", () => {
    expect(rewriteLinks("[o](02-other.md#a-heading)", { "02-other.md": "other" })).toBe("[o](/help/other/#a-heading)");
    expect(rewriteLinks("[m](99-x.md)", {})).toBe("[m](#)");
    expect(slugify("Can I upload my own list?")).toBe("can-i-upload-my-own-list");
  });
});
