import type { ChatMessage } from "@/lib/api/types";

/**
 * Article titles to show under an assistant answer (Phase 2 help center).
 *
 * The API already returns one source per article, in citation order; this
 * still de-duplicates by title and drops blanks, so a reloaded transcript
 * from an older API build (no `sources` field) or a malformed entry renders
 * nothing rather than an empty "Sources:" line. User messages never have
 * sources -- only the assistant cites.
 */
export function sourceTitlesFor(
  message: Pick<ChatMessage, "role" | "sources">,
): string[] {
  if (message.role !== "assistant") return [];
  const seen = new Set<string>();
  const titles: string[] = [];
  for (const source of message.sources ?? []) {
    const title = (source?.title ?? "").trim();
    if (!title || seen.has(title)) continue;
    seen.add(title);
    titles.push(title);
  }
  return titles;
}
