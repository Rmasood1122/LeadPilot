/**
 * Inline formatting for content-page strings: **bold**, `code`, [label](href).
 *
 * Everything else is plain text, and React escapes it, so content can never
 * inject markup. A link is kept only when its href is a site path ("/…",
 * "#…") or an https URL; any other scheme (javascript:, data:, http:) is
 * rendered as its label alone.
 */

import Link from "next/link";
import type { ReactNode } from "react";

const TOKEN = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)\s]+\))/g;

export function safeHref(href: string): string | null {
  if (href.startsWith("/") && !href.startsWith("//")) return href;
  if (href.startsWith("#")) return href;
  if (/^https:\/\/[^\s]+$/.test(href)) return href;
  return null;
}

export function RichText({ text }: { text: string }): ReactNode {
  const parts = text.split(TOKEN).filter((p) => p !== "");
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold text-white">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i} className="rounded bg-white/10 px-1 py-0.5 text-[0.9em]">{part.slice(1, -1)}</code>;
    }
    const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(part);
    if (link) {
      const [, label, rawHref] = link;
      const href = safeHref(rawHref);
      if (!href) return <span key={i}>{label}</span>;
      if (href.startsWith("/") || href.startsWith("#")) {
        return <Link key={i} href={href} className="text-blue-400 underline hover:text-blue-300">{label}</Link>;
      }
      return (
        <a key={i} href={href} className="text-blue-400 underline hover:text-blue-300" rel="noopener">
          {label}
        </a>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

/** The same string as a reader sees it, for JSON-LD answers (which must match
 *  the visible text) and meta descriptions. */
export function plainText(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, "$1");
}
