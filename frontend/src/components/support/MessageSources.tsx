"use client";

import { BookOpen } from "lucide-react";

import type { ChatMessage } from "@/lib/api/types";
import { sourceTitlesFor } from "@/lib/support/sources";

/**
 * "Sources" under an assistant answer: the help-center articles it was drawn
 * from (Phase 2). Renders nothing when there are none -- refusals, ticket
 * offers and user turns cite nothing, and an empty label would imply a
 * source that does not exist.
 */
export function MessageSources({
  message,
}: {
  message: Pick<ChatMessage, "role" | "sources">;
}) {
  const titles = sourceTitlesFor(message);
  if (!titles.length) return null;
  return (
    <div data-testid="support-sources" className="mt-2 border-t border-border pt-1.5">
      <p className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground">
        <BookOpen size={11} aria-hidden="true" />
        Sources
      </p>
      <ul aria-label="Sources" className="mt-0.5 space-y-0.5 text-[11px] text-muted-foreground">
        {titles.map((title) => (
          <li key={title}>{title}</li>
        ))}
      </ul>
    </div>
  );
}
