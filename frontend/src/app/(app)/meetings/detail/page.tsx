"use client";

/** Engagement Hub, Feature 3 — the meeting room for one meeting.
 *
 * ROUTE SHAPE: `/meetings/detail?id=...`, not `/meetings/[id]`. The brief asks
 * for the dynamic segment, and this frontend cannot have one: next.config.js
 * sets `output: 'export'` (it is what Capacitor bundles into the APK), so
 * every route must be enumerable at build time and a `[id]` segment would need
 * `generateStaticParams` over meetings that do not exist yet. There are no
 * `[param]` routes anywhere in this app for exactly that reason —
 * `/strategies/detail?id=` is the established pattern and this follows it.
 *
 * THE SUMMARY PANEL SLIDES IN AFTER THE MEETING ENDS. It is queued in the
 * background by /end, so this page polls while a completed meeting has no
 * summary yet — and stops the moment one lands, rather than polling forever
 * on a meeting whose summary genuinely failed.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileText } from "lucide-react";

import {
  endMeeting,
  generateSummary,
  getMeeting,
  saveActionItems,
  saveNotes,
  startMeeting,
  type ActionItem,
} from "@/lib/api/meetings";
import { AISummaryPanel } from "@/components/meetings/AISummaryPanel";
import { MeetingRoom } from "@/components/meetings/MeetingRoom";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

/** How often to look for a summary the background task is still writing. */
const SUMMARY_POLL_MS = 5_000;

export default function MeetingDetailPage() {
  const params = useSearchParams();
  const id = params.get("id");
  const toast = useToast();
  const queryClient = useQueryClient();
  const [awaitingSummary, setAwaitingSummary] = useState(false);

  const query = useQuery({
    queryKey: ["meeting", id],
    queryFn: () => getMeeting(id as string),
    enabled: !!id,
    refetchInterval: awaitingSummary ? SUMMARY_POLL_MS : false,
  });

  const meeting = query.data;

  // Stop polling as soon as the summary arrives. Without this the page keeps
  // asking every five seconds for as long as the tab is open.
  useEffect(() => {
    if (awaitingSummary && meeting?.summary) setAwaitingSummary(false);
  }, [awaitingSummary, meeting?.summary]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["meeting", id] });
    queryClient.invalidateQueries({ queryKey: ["meetings"] });
  };

  const start = useMutation({
    mutationFn: () => startMeeting(id as string),
    onSuccess: refresh,
    onError: (error) => toast((error as Error).message, "error"),
  });

  const end = useMutation({
    mutationFn: () => endMeeting(id as string, true),
    onSuccess: () => {
      refresh();
      setAwaitingSummary(true);
      toast("Meeting ended — writing the summary", "info");
    },
    onError: (error) => toast((error as Error).message, "error"),
  });

  const summarise = useMutation({
    mutationFn: () => generateSummary(id as string),
    onSuccess: () => {
      refresh();
      toast("Summary ready", "success");
    },
    onError: (error) => toast((error as Error).message, "error"),
  });

  const persistActionItems = useMutation({
    mutationFn: (items: ActionItem[]) => saveActionItems(id as string, items),
    onSuccess: refresh,
    onError: (error) => toast((error as Error).message, "error"),
  });

  if (!id) {
    return (
      <p className="text-sm text-muted-foreground">
        No meeting selected. Open one from{" "}
        <Link href="/meetings" className="underline underline-offset-2">
          Meetings
        </Link>
        .
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link
          href="/meetings"
          className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={12} aria-hidden="true" />
          Meetings
        </Link>
        <Link
          href={`/meetings/transcript?id=${id}`}
          className="inline-flex h-8 items-center gap-2 rounded border border-border px-3 text-xs font-medium hover:bg-muted"
        >
          <FileText size={14} aria-hidden="true" />
          Transcript
        </Link>
      </div>

      <AsyncState isLoading={query.isLoading} error={query.error}>
        {meeting && (
          <>
            <MeetingRoom
              meeting={meeting}
              isBusy={start.isPending || end.isPending}
              onStart={() => start.mutate()}
              onEnd={() => end.mutate()}
              onSaveNotes={(notes) => saveNotes(id, notes)}
            />

            {/* The panel appears once the meeting is over — before that there
                is nothing to summarise, and offering the button mid-call
                invites somebody to spend a model call on half a conversation. */}
            {meeting.status === "completed" && (
              <AISummaryPanel
                summary={meeting.summary}
                keyPoints={meeting.key_points}
                nextSteps={meeting.next_steps}
                sentiment={meeting.sentiment}
                actionItems={meeting.action_items}
                onSaveActionItems={(items) => persistActionItems.mutate(items)}
                onGenerate={() => summarise.mutate()}
                isGenerating={summarise.isPending || awaitingSummary}
              />
            )}
          </>
        )}
      </AsyncState>
    </div>
  );
}
