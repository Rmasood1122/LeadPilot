"use client";

/** What the model made of the call: summary, key points, action items,
 *  next steps, and how the prospect seemed.
 *
 * IT SAYS WHERE THE WORDS CAME FROM. Everything in here is generated, and the
 * panel is labelled as such rather than presenting it as the user's own
 * record — the user's own record is `raw_notes`, which is a separate field the
 * model never writes to. A summary that reads like a transcript of what the
 * user believes happened, when it is actually a model's reading of it, is the
 * failure this feature has to avoid.
 *
 * The empty state is a button, not a spinner-forever: /end queues the summary
 * in the background, so "not here yet" is the normal state for the first few
 * seconds after a call and a permanent state if the queue is down.
 */

import { Sparkles } from "lucide-react";

import type { ActionItem } from "@/lib/api/meetings";
import { ActionItemsList } from "./ActionItemsList";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const SENTIMENT_TONE: Record<string, "success" | "warning" | "destructive" | "default"> =
  {
    positive: "success",
    neutral: "default",
    mixed: "warning",
    negative: "destructive",
    unknown: "default",
  };

export function AISummaryPanel({
  summary,
  keyPoints,
  nextSteps,
  sentiment,
  actionItems,
  onSaveActionItems,
  onGenerate,
  isGenerating,
}: {
  summary: string | null;
  keyPoints: string[] | null;
  nextSteps: string[] | null;
  sentiment: string | null;
  actionItems: ActionItem[] | null;
  onSaveActionItems: (items: ActionItem[]) => void;
  onGenerate: () => void;
  isGenerating: boolean;
}) {
  const hasSummary = !!summary?.trim();

  return (
    <section
      aria-label="AI summary"
      className="space-y-4 rounded border border-border bg-card p-4"
    >
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Sparkles size={14} aria-hidden="true" />
          AI summary
        </h2>
        <div className="flex items-center gap-2">
          {sentiment && sentiment !== "unknown" && (
            <Badge tone={SENTIMENT_TONE[sentiment] ?? "default"}>
              {sentiment}
            </Badge>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={onGenerate}
            disabled={isGenerating}
          >
            {isGenerating
              ? "Generating…"
              : hasSummary
                ? "Regenerate"
                : "Generate"}
          </Button>
        </div>
      </div>

      {!hasSummary ? (
        <p className="text-sm text-muted-foreground">
          No summary yet. It is generated from the transcript and your live
          notes once the meeting ends — press Generate to run it now.
        </p>
      ) : (
        <>
          <p className="whitespace-pre-wrap text-sm">{summary}</p>

          {!!keyPoints?.length && (
            <div>
              <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Key points
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {keyPoints.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>
          )}

          {!!nextSteps?.length && (
            <div>
              <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Next steps
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {nextSteps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}

      <div>
        <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Action items
        </h3>
        <ActionItemsList
          items={actionItems ?? []}
          onSave={onSaveActionItems}
        />
      </div>

      <p className="text-xs text-muted-foreground">
        Generated from the transcript and your notes. Your own notes are kept
        separately and are never rewritten by this.
      </p>
    </section>
  );
}
