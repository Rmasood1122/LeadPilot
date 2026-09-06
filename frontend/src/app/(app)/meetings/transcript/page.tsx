"use client";

/** Engagement Hub, Feature 3 — the full transcript of one meeting.
 *
 * `/meetings/transcript?id=...` rather than `/meetings/[id]/transcript` — see
 * the note in ../detail/page.tsx: this frontend is a static export and cannot
 * have dynamic route segments.
 *
 * A page of its own rather than a tab inside the meeting room, because the
 * room is a working surface used DURING a call and a transcript is read after
 * one. Loading a few thousand lines into the room would also mean shipping
 * them to every meeting the user opens, including the ones about to start.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import { getMeeting } from "@/lib/api/meetings";
import { TranscriptViewer } from "@/components/meetings/TranscriptViewer";
import { AsyncState } from "@/components/ui/skeleton";
import { formatTime } from "@/lib/calendar/grid";

export default function MeetingTranscriptPage() {
  const params = useSearchParams();
  const id = params.get("id");

  const query = useQuery({
    queryKey: ["meeting", id],
    queryFn: () => getMeeting(id as string),
    enabled: !!id,
  });

  const meeting = query.data;

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
      <Link
        href={`/meetings/detail?id=${id}`}
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground print:hidden"
      >
        <ArrowLeft size={12} aria-hidden="true" />
        Back to the meeting
      </Link>

      <AsyncState isLoading={query.isLoading} error={query.error}>
        {meeting && (
          <>
            <header>
              <h1 className="text-xl font-semibold">
                {meeting.title ?? "Meeting"}
              </h1>
              <p className="text-sm text-muted-foreground">
                {new Date(meeting.start_at).toLocaleDateString()} ·{" "}
                {formatTime(new Date(meeting.start_at))}
                {meeting.recording_url && (
                  <>
                    {" · "}
                    <a
                      href={meeting.recording_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="underline underline-offset-2"
                    >
                      Recording
                    </a>
                  </>
                )}
              </p>
            </header>

            <TranscriptViewer
              transcript={meeting.transcript}
              title={meeting.title ?? "Meeting"}
            />
          </>
        )}
      </AsyncState>
    </div>
  );
}
