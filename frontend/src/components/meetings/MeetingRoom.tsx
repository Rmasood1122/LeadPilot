"use client";

/** The meeting room: everything you need while the call is happening.
 *
 * Left   who you are talking to
 * Centre live notes, autosaved
 * Right  how to join
 * Bottom start / end, and the timer
 *
 * THE NOTES AUTOSAVE IS THE PART THAT MATTERS. Somebody types into this
 * textarea for forty minutes while talking. A save that only happens on blur
 * loses everything to a closed tab; a save on every keystroke is 3,000
 * requests. So: a 10-second debounce, a save on unmount, and a visible
 * "saving / saved" state so the user can tell before they close the tab.
 *
 * The right panel is NOT an iframe. Google Meet, Zoom and Teams all refuse to
 * be framed (X-Frame-Options / frame-ancestors), so an embed renders an empty
 * box that looks broken. PlatformLauncher explains that trade in full.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { CircleDot, Clock, Play, Square, User } from "lucide-react";

import type { MeetingDetail } from "@/lib/api/meetings";
import { PlatformLauncher } from "./PlatformLauncher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import { countdown, elapsed, formatTime } from "@/lib/calendar/grid";

const AUTOSAVE_MS = 10_000;

type SaveState = "idle" | "saving" | "saved";

export function MeetingRoom({
  meeting,
  onSaveNotes,
  onStart,
  onEnd,
  isBusy,
}: {
  meeting: MeetingDetail;
  onSaveNotes: (notes: string) => Promise<unknown>;
  onStart: () => void;
  onEnd: () => void;
  isBusy: boolean;
}) {
  const [notes, setNotes] = useState(meeting.raw_notes ?? "");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const timer = useRef<number | null>(null);
  // The last value actually persisted, so unmount does not re-send text the
  // debounce already saved.
  const savedRef = useRef(meeting.raw_notes ?? "");
  const notesRef = useRef(notes);
  notesRef.current = notes;

  const flush = useCallback(async () => {
    if (notesRef.current === savedRef.current) return;
    setSaveState("saving");
    const pending = notesRef.current;
    try {
      await onSaveNotes(pending);
      savedRef.current = pending;
      setSaveState("saved");
    } catch {
      // Left as "saving" would claim work in progress that is not happening.
      // "idle" plus unchanged text is honest: the next debounce retries.
      setSaveState("idle");
    }
  }, [onSaveNotes]);

  useEffect(() => {
    if (notes === savedRef.current) return;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void flush(), AUTOSAVE_MS);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
  }, [notes, flush]);

  // Save on the way out. Closing a tab mid-call must not cost the notes.
  useEffect(
    () => () => {
      void flush();
    },
    [flush],
  );

  const startedAt = meeting.actual_start_at
    ? new Date(meeting.actual_start_at).getTime()
    : null;
  const running = meeting.status === "in_progress";

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[240px_1fr_280px]">
        {/* ── Who ─────────────────────────────────────────────────────── */}
        <aside className="space-y-3 rounded border border-border bg-card p-4 text-sm">
          <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Meeting
          </h2>
          <p className="font-medium">{meeting.title ?? "Meeting"}</p>
          <p className="flex items-center gap-1 text-muted-foreground">
            <Clock size={14} aria-hidden="true" />
            {formatTime(new Date(meeting.start_at))}–
            {formatTime(new Date(meeting.end_at))}
          </p>
          <Badge tone={running ? "warning" : "default"}>
            {meeting.status.replace(/_/g, " ")}
          </Badge>

          {meeting.participants.length > 0 && (
            <div>
              <h3 className="mb-1 mt-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Participants
              </h3>
              <ul className="space-y-1">
                {meeting.participants.map((participant) => (
                  <li
                    key={participant.id}
                    className="flex items-center gap-2 truncate"
                  >
                    <User
                      size={12}
                      aria-hidden="true"
                      className="shrink-0 text-muted-foreground"
                    />
                    <span className="truncate">
                      {participant.name ?? participant.email ?? "—"}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {participant.role}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>

        {/* ── Notes ───────────────────────────────────────────────────── */}
        <section aria-label="Live notes" className="flex flex-col">
          <div className="mb-1 flex items-center justify-between">
            <h2 className="text-sm font-medium">Live notes</h2>
            <span
              aria-live="polite"
              className="text-xs text-muted-foreground"
            >
              {saveState === "saving"
                ? "Saving…"
                : saveState === "saved"
                  ? "Saved"
                  : notes !== savedRef.current
                    ? "Unsaved"
                    : ""}
            </span>
          </div>
          <Textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            onBlur={() => void flush()}
            placeholder="What are they saying? Type freely — this saves itself."
            aria-label="Live notes"
            className="min-h-[320px] flex-1 font-mono text-sm"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Your own notes. The AI summary is written to a separate field and
            never overwrites this.
          </p>
        </section>

        {/* ── Join ────────────────────────────────────────────────────── */}
        <aside className="space-y-3">
          <h2 className="text-sm font-medium">Join</h2>
          <PlatformLauncher
            platform={meeting.platform}
            meetingUrl={meeting.meeting_url}
          />
        </aside>
      </div>

      {/* ── Bottom bar ───────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-border bg-card p-3">
        <MeetingTimer startedAtMs={startedAt} running={running} meeting={meeting} />
        <div className="flex gap-2">
          {meeting.status !== "completed" && (
            <Button
              variant={running ? "outline" : "default"}
              disabled={isBusy || running}
              onClick={onStart}
            >
              <Play size={16} aria-hidden="true" />
              {running ? "Running" : "Start meeting"}
            </Button>
          )}
          <Button
            variant="destructive"
            disabled={isBusy || meeting.status === "completed"}
            onClick={onEnd}
          >
            <Square size={16} aria-hidden="true" />
            End meeting
          </Button>
        </div>
      </div>
    </div>
  );
}

function MeetingTimer({
  startedAtMs,
  running,
  meeting,
}: {
  startedAtMs: number | null;
  running: boolean;
  meeting: MeetingDetail;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return;
    // One interval, only while the meeting is actually running. A timer left
    // ticking on a completed meeting is a wakeup a second, forever, on a tab
    // somebody left open.
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [running]);

  if (running && startedAtMs) {
    return (
      <p className="flex items-center gap-2 text-sm tabular-nums">
        <CircleDot
          size={14}
          aria-hidden="true"
          className="text-[rgb(var(--destructive))]"
        />
        <span className="sr-only">Elapsed:</span>
        {elapsed(startedAtMs, now)}
      </p>
    );
  }

  if (meeting.status === "completed") {
    const from = meeting.actual_start_at
      ? new Date(meeting.actual_start_at).getTime()
      : null;
    const to = meeting.actual_end_at
      ? new Date(meeting.actual_end_at).getTime()
      : null;
    return (
      <p className="text-sm text-muted-foreground tabular-nums">
        Ran {from && to ? elapsed(from, to) : "—"}
      </p>
    );
  }

  const upcoming = countdown(new Date(meeting.start_at));
  return (
    <p className="text-sm text-muted-foreground">
      {upcoming ? `Starts ${upcoming}` : "Not started"}
    </p>
  );
}
