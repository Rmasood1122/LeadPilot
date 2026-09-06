"use client";

/** Engagement Hub, Feature 3 — every meeting, upcoming and past.
 *
 * Two lists rather than one sorted list. They answer different questions:
 * "what is next and can I get into it" versus "what happened and what did we
 * agree". Merging them means the thing you need in the next ten minutes is
 * somewhere in the middle of a scroll.
 *
 * "Upcoming" is decided by `end_at`, not `start_at` — a call that started ten
 * minutes ago and runs for an hour is still the one you need the Join button
 * for. The backend applies the same rule; see its list handler.
 */

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText, Video } from "lucide-react";

import { listMeetings, type Meeting } from "@/lib/api/meetings";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";
import { countdown, formatTime } from "@/lib/calendar/grid";

const STATUS_TONE: Record<string, "success" | "warning" | "destructive" | "default"> =
  {
    scheduled: "default",
    in_progress: "warning",
    completed: "success",
    cancelled: "destructive",
  };

/** Refetched on an interval because the countdown on an upcoming meeting is
 *  only as honest as the data behind it, and because a meeting somebody else
 *  cancelled should stop offering a Join button. 60s: the same fallback
 *  cadence the CRM hooks use. */
const POLL_MS = 60_000;

export default function MeetingsPage() {
  const [tab, setTab] = useState<"upcoming" | "past">("upcoming");

  const query = useQuery({
    queryKey: ["meetings", tab],
    queryFn: () => listMeetings({ upcoming: tab === "upcoming" }),
    refetchInterval: POLL_MS,
    placeholderData: (previous) => previous,
  });

  const meetings = query.data ?? [];

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-xl font-semibold">Meetings</h1>
        <p className="text-sm text-muted-foreground">
          Join, take notes, and keep what was agreed.
        </p>
      </header>

      <div role="tablist" aria-label="Meetings" className="flex gap-1">
        {(["upcoming", "past"] as const).map((value) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={
              tab === value
                ? "rounded bg-[rgb(var(--primary))] px-3 py-1.5 text-sm font-medium text-primary-foreground"
                : "rounded px-3 py-1.5 text-sm text-muted-foreground hover:bg-muted"
            }
          >
            {value === "upcoming" ? "Upcoming" : "Past"}
          </button>
        ))}
      </div>

      <AsyncState
        isLoading={query.isLoading}
        error={query.error}
        empty={meetings.length === 0}
        emptyLabel={
          tab === "upcoming"
            ? "Nothing booked yet. Share a booking page to start taking calls."
            : "No past meetings."
        }
      >
        <ul className="space-y-2">
          {meetings.map((meeting) => (
            <li key={meeting.id}>
              <MeetingRow meeting={meeting} isUpcoming={tab === "upcoming"} />
            </li>
          ))}
        </ul>
      </AsyncState>
    </div>
  );
}

function MeetingRow({
  meeting,
  isUpcoming,
}: {
  meeting: Meeting;
  isUpcoming: boolean;
}) {
  const start = new Date(meeting.start_at);
  const until = countdown(start);

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-gutter">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate font-medium">{meeting.title ?? "Meeting"}</p>
            <Badge tone={STATUS_TONE[meeting.status] ?? "default"}>
              {meeting.status.replace(/_/g, " ")}
            </Badge>
            {meeting.sentiment && meeting.sentiment !== "unknown" && (
              <Badge tone="default">{meeting.sentiment}</Badge>
            )}
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {start.toLocaleDateString()} · {formatTime(start)}
            {isUpcoming && until && (
              <span className="ml-2 font-medium text-foreground">{until}</span>
            )}
            <span className="ml-2">· {meeting.platform.replace(/_/g, " ")}</span>
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {isUpcoming && meeting.meeting_url && (
            <a
              href={meeting.meeting_url}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex h-8 items-center gap-2 rounded bg-[rgb(var(--primary))] px-3 text-xs font-medium text-primary-foreground hover:opacity-90"
            >
              <ExternalLink size={14} aria-hidden="true" />
              Join meeting
            </a>
          )}
          <Link
            href={`/meetings/detail?id=${meeting.id}`}
            className="inline-flex h-8 items-center gap-2 rounded border border-border px-3 text-xs font-medium hover:bg-muted"
          >
            <Video size={14} aria-hidden="true" />
            {isUpcoming ? "Open room" : "View summary"}
          </Link>
          {!isUpcoming && (
            <Link
              href={`/meetings/transcript?id=${meeting.id}`}
              className="inline-flex h-8 items-center gap-2 rounded border border-border px-3 text-xs font-medium hover:bg-muted"
            >
              <FileText size={14} aria-hidden="true" />
              Transcript
            </Link>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
