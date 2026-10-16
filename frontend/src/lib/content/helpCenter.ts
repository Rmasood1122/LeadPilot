/**
 * The published help center: src/content/help-center/NN-<id>.md (a copy of
 * docs/help-center/, made by scripts/help/sync_help_center.mjs) parsed into
 * articles. Build-time only (node:fs), used by the static /help/ pages.
 */

import fs from "node:fs";
import path from "node:path";

import { CHECKOUT_LIVE, capabilitiesWithStatus } from "@/lib/productFacts";

import { type Article, parseArticle } from "./markdown";

export const HELP_DIR = path.join(process.cwd(), "src", "content", "help-center");
const ARTICLE = /^\d\d-[a-z0-9-]+\.md$/;

export interface HelpArticle extends Article {
  file: string;
}

export function helpArticles(): HelpArticle[] {
  const files = fs.readdirSync(HELP_DIR).filter((f) => ARTICLE.test(f)).sort();
  const raw = files.map((f) => ({ file: f, text: fs.readFileSync(path.join(HELP_DIR, f), "utf8") }));
  const fileToId: Record<string, string> = {};
  for (const { file, text } of raw) {
    const id = /^id:\s*(\S+)/m.exec(text)?.[1];
    if (id) fileToId[file] = id;
  }
  return raw.map(({ file, text }) => ({ ...parseArticle(text, fileToId), file }));
}

export function helpArticle(id: string): HelpArticle {
  const found = helpArticles().find((a) => a.id === id);
  if (!found) throw new Error(`unknown help article ${id}`);
  return found;
}

/** Shown on every article: the articles describe what the code does, and
 *  this line says what is not live today (product-facts.json), so a help
 *  page never contradicts the marketing pages. */
export function helpStatusNote(): string {
  const notLive = capabilitiesWithStatus("simulated_only").map((c) => c.name);
  const parts = [
    notLive.length
      ? `Not live yet: ${notLive.join("; ")}. Where this article describes them, they are built and tested only against simulated services.`
      : "",
    CHECKOUT_LIVE ? "" : "Free trials and online plan changes described here start through online checkout, which is not live yet; to start, [book a call](/contact).",
    "Features marked off by default must be switched on by an administrator. See [known limitations](/help/known-limitations).",
  ];
  return parts.filter(Boolean).join(" ");
}
