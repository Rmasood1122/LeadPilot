/**
 * Parses a help-center article (docs/help-center/NN-<id>.md, copied into
 * src/content/help-center/) into the content model (./types).
 *
 * Supported, because it is all the articles use (checked 2026-10-16): YAML-ish
 * front matter, one "# " title, "## " sections, "### " subheadings,
 * paragraphs, "- " bullets, "1. " numbered lists and pipe tables. Inline
 * **bold**, `code` and [label](href) are left for RichText. Links to another
 * article ("20-compliance.md#anchor") are rewritten to its page ("/help/compliance/#anchor").
 */

import type { Block, Section } from "./types";

export interface Article {
  id: string;
  title: string;
  audience: string;
  lastVerified: string;
  lead: string[];
  sections: Section[];
}

/** GitHub-style heading anchor: "Do I approve automatic sending every day?" → "do-i-approve-automatic-sending-every-day". */
export function slugify(heading: string): string {
  return heading
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s-]/gu, "")
    .trim()
    .replace(/\s/g, "-");
}

export function frontMatter(raw: string): { meta: Record<string, string>; body: string } {
  const m = /^---\n([\s\S]*?)\n---\n/.exec(raw);
  if (!m) return { meta: {}, body: raw };
  const meta: Record<string, string> = {};
  for (const line of m[1].split("\n")) {
    const kv = /^([a-z_]+):\s*(.*)$/.exec(line);
    if (kv && kv[2] !== "") meta[kv[1]] = kv[2].trim();
  }
  return { meta, body: raw.slice(m[0].length) };
}

/** "NN-name.md[#anchor]" → "/help/<id>/[#anchor]"; unknown .md links lose their href. */
export function rewriteLinks(text: string, fileToId: Record<string, string>): string {
  return text.replace(/\]\(([^)\s]+\.md)(#[^)\s]*)?\)/g, (whole, file: string, anchor = "") => {
    const id = fileToId[file.replace(/^\.\//, "")];
    return id ? `](/help/${id}/${anchor})` : `](#)`;
  });
}

const isTableRow = (l: string) => l.trim().startsWith("|") && l.trim().endsWith("|");
const isDivider = (l: string) => /^\s*\|(\s*:?-{3,}:?\s*\|)+\s*$/.test(l);
const cells = (l: string) => l.trim().slice(1, -1).split("|").map((c) => c.trim());

export function parseArticle(raw: string, fileToId: Record<string, string>): Article {
  const { meta, body } = frontMatter(raw);
  const lines = rewriteLinks(body, fileToId).split("\n");
  let title = meta.title ?? "";
  const lead: string[] = [];
  const sections: Section[] = [];
  let current: Section | null = null;
  const push = (b: Block) => {
    if (current) current.blocks.push(b);
    else if (b.kind === "p") lead.push(b.text);
    else {
      current = { heading: "Overview", blocks: [b] };
      sections.push(current);
    }
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === "") { i++; continue; }
    if (line.startsWith("# ")) { title = line.slice(2).trim(); i++; continue; }
    if (line.startsWith("## ")) {
      const heading = line.slice(3).trim();
      current = { heading, id: slugify(heading), blocks: [] };
      sections.push(current);
      i++;
      continue;
    }
    if (line.startsWith("### ")) { push({ kind: "h3", text: line.slice(4).trim() }); i++; continue; }
    if (isTableRow(line) && i + 1 < lines.length && isDivider(lines[i + 1])) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && isTableRow(lines[i])) { rows.push(cells(lines[i])); i++; }
      push({ kind: "table", head, rows });
      continue;
    }
    const bullet = /^\s*[-*] (.*)$/;
    const numbered = /^\s*\d+\. (.*)$/;
    if (bullet.test(line) || numbered.test(line)) {
      const kind = bullet.test(line) ? "ul" : "ol";
      const re = kind === "ul" ? bullet : numbered;
      const items: string[] = [];
      while (i < lines.length && lines[i].trim() !== "" && (re.test(lines[i]) || /^\s{2,}\S/.test(lines[i]))) {
        const m = re.exec(lines[i]);
        if (m) items.push(m[1].trim());
        else items[items.length - 1] += ` ${lines[i].trim()}`;
        i++;
      }
      push({ kind, items });
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length && lines[i].trim() !== "" && !/^#{1,3} /.test(lines[i]) &&
      !/^\s*([-*]|\d+\.) /.test(lines[i]) && !isTableRow(lines[i])
    ) { para.push(lines[i].trim()); i++; }
    push({ kind: "p", text: para.join(" ") });
  }

  return {
    id: meta.id ?? "",
    title,
    audience: meta.audience ?? "",
    lastVerified: meta.last_verified ?? "",
    lead,
    sections,
  };
}
