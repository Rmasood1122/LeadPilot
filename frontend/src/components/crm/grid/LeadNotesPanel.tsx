"use client";

/** Notes, activity and meetings for one lead, opened from the grid's notes cell.
 *
 * Uses the existing Modal primitive rather than a bespoke drawer — the app
 * already has one, it already traps focus and handles Escape, and a second
 * overlay implementation is a second set of accessibility bugs.
 *
 * THE MEETINGS TAB (Engagement Hub, Feature 4) is here rather than on a screen
 * of its own because this panel is what a user opens right before their next
 * touch on a lead, and "what did we agree on the call" is the single most
 * useful thing to know at that moment. It loads lazily — the query only fires
 * once the tab is opened, so the common case (someone adding a note) does not
 * pay for a meetings request.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, ExternalLink, Trash2 } from "lucide-react";
import Link from "next/link";

import { getLeadActivity } from "@/lib/api/crm";
import { useCreateNote, useCrmNotes, useDeleteNote } from "@/lib/api/crm-hooks";
import { listBookingPages, bookingPageUrl } from "@/lib/api/calendar";
import { listMeetings, type Meeting } from "@/lib/api/meetings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

type Tab = "notes" | "meetings";

export function LeadNotesPanel({
  leadId,
  onClose,
}: {
  leadId: string;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("notes");

  return (
    <Modal open onClose={onClose} title="Lead">
      <div className="space-y-4 text-sm">
        <div role="tablist" aria-label="Lead detail" className="flex gap-1">
          {(
            [
              ["notes", "Notes & activity"],
              ["meetings", "Meetings"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              role="tab"
              aria-selected={tab === value}
              onClick={() => setTab(value)}
              className={cn(
                "rounded px-3 py-1.5 text-sm",
                tab === value
                  ? "bg-[rgb(var(--primary))] font-medium text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted",
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "notes" ? (
          <NotesTab leadId={leadId} />
        ) : (
          <MeetingsTab leadId={leadId} />
        )}
      </div>
    </Modal>
  );
}

function NotesTab({ leadId }: { leadId: string }) {
  const [draft, setDraft] = useState("");
  const toast = useToast();
  const { data: notes, isLoading } = useCrmNotes(leadId);
  const createNote = useCreateNote(leadId);
  const deleteNote = useDeleteNote(leadId);

  const { data: activity } = useQuery({
    queryKey: ["crm-activity", "lead", leadId],
    queryFn: () => getLeadActivity(leadId),
  });

  const submit = () => {
    const body = draft.trim();
    if (!body) return;
    createNote.mutate(body, {
      onSuccess: () => setDraft(""),
      onError: (error) =>
        toast((error as Error).message ?? "Could not save note", "error"),
    });
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            // Ctrl/Cmd+Enter submits; plain Enter inserts a newline, because
            // notes are frequently multi-line and losing a paragraph to a
            // stray Enter is worse than an extra keystroke.
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              submit();
            }
          }}
          placeholder="What happened? (Ctrl+Enter to save)"
          rows={3}
          aria-label="New note"
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={!draft.trim() || createNote.isPending}
            onClick={submit}
          >
            Add note
          </Button>
        </div>
      </div>

      <section aria-label="Notes">
        <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Notes
        </h3>
        {isLoading ? (
          <p className="text-muted-foreground">Loading…</p>
        ) : notes?.items.length ? (
          <ul className="space-y-2">
            {notes.items.map((note) => (
              <li
                key={note.id}
                className="flex items-start gap-2 rounded border border-border p-2"
              >
                <div className="min-w-0 flex-1">
                  <p className="whitespace-pre-wrap break-words">{note.body}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {note.created_at
                      ? new Date(note.created_at).toLocaleString()
                      : ""}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => deleteNote.mutate(note.id)}
                  aria-label="Delete note"
                  className="text-muted-foreground hover:text-[rgb(var(--destructive))]"
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">No notes yet.</p>
        )}
      </section>

      <section aria-label="Activity">
        <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Activity
        </h3>
        {activity?.items.length ? (
          <ol className="space-y-1 text-xs">
            {activity.items.map((item) => (
              <li key={item.id} className="flex justify-between gap-3">
                <span className="min-w-0 truncate text-muted-foreground">
                  {item.kind.replace(/_/g, " ")}
                  {item.to_value ? `: ${item.to_value}` : ""}
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {item.ts ? new Date(item.ts).toLocaleDateString() : ""}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-xs text-muted-foreground">Nothing recorded yet.</p>
        )}
      </section>
    </div>
  );
}

function MeetingsTab({ leadId }: { leadId: string }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["meetings", "lead", leadId],
    queryFn: () => listMeetings({ leadId }),
  });

  const meetings = data ?? [];

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => setPicking(true)}>
          <CalendarPlus size={14} aria-hidden="true" />
          Book new meeting
        </Button>
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Loading…</p>
      ) : meetings.length === 0 ? (
        <p className="text-muted-foreground">
          No meetings with this lead yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {meetings.map((meeting) => (
            <MeetingRow
              key={meeting.id}
              meeting={meeting}
              expanded={expanded === meeting.id}
              onToggle={() =>
                setExpanded(expanded === meeting.id ? null : meeting.id)
              }
            />
          ))}
        </ul>
      )}

      {picking && <BookingPagePicker onClose={() => setPicking(false)} />}
    </div>
  );
}

function MeetingRow({
  meeting,
  expanded,
  onToggle,
}: {
  meeting: Meeting;
  expanded: boolean;
  onToggle: () => void;
}) {
  const start = new Date(meeting.start_at);
  return (
    <li className="rounded border border-border">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-center justify-between gap-2 px-2 py-1.5 text-left"
      >
        <span className="min-w-0 truncate">
          {meeting.title ?? "Meeting"}
          <span className="ml-2 text-xs text-muted-foreground">
            {start.toLocaleDateString()}
          </span>
        </span>
        <Badge tone={meeting.status === "completed" ? "success" : "default"}>
          {meeting.status.replace(/_/g, " ")}
        </Badge>
      </button>

      {expanded && (
        <div className="space-y-2 border-t border-border px-2 py-2 text-xs">
          {meeting.summary ? (
            <p className="whitespace-pre-wrap">{meeting.summary}</p>
          ) : (
            <p className="text-muted-foreground">
              No summary for this meeting.
            </p>
          )}
          {!!meeting.action_items?.length && (
            <ul className="list-disc space-y-0.5 pl-4">
              {meeting.action_items.map((item, index) => (
                <li
                  key={`${item.text}-${index}`}
                  className={item.done ? "line-through opacity-60" : undefined}
                >
                  {item.text}
                </li>
              ))}
            </ul>
          )}
          <Link
            href={`/meetings/detail?id=${meeting.id}`}
            className="inline-flex items-center gap-1 underline underline-offset-2"
          >
            <ExternalLink size={12} aria-hidden="true" />
            Open meeting
          </Link>
        </div>
      )}
    </li>
  );
}

/** Which booking page to send them?
 *
 *  Deliberately a link picker rather than a "book on their behalf" form. The
 *  prospect chooses the time — that is the entire point of a booking page, and
 *  a seller picking a slot for somebody produces a meeting half of them do not
 *  turn up to.
 */
function BookingPagePicker({ onClose }: { onClose: () => void }) {
  const toast = useToast();
  const { data, isLoading } = useQuery({
    queryKey: ["booking-pages"],
    queryFn: listBookingPages,
  });

  const active = (data ?? []).filter((page) => page.is_active);

  const copy = async (slug: string) => {
    const url = bookingPageUrl(slug);
    try {
      await navigator.clipboard.writeText(url);
      toast("Link copied — paste it into your next message", "success");
    } catch {
      toast(url, "info");
    }
    onClose();
  };

  return (
    <Modal open onClose={onClose} title="Send a booking link">
      <div className="space-y-2 text-sm">
        {isLoading ? (
          <p className="text-muted-foreground">Loading…</p>
        ) : active.length === 0 ? (
          <p className="text-muted-foreground">
            No live booking pages.{" "}
            <Link
              href="/calendar/booking-pages"
              className="underline underline-offset-2"
            >
              Create one
            </Link>{" "}
            first.
          </p>
        ) : (
          <ul className="space-y-1">
            {active.map((page) => (
              <li key={page.id}>
                <button
                  type="button"
                  onClick={() => copy(page.slug)}
                  className="flex w-full items-center justify-between gap-2 rounded border border-border px-2 py-1.5 text-left hover:bg-muted"
                >
                  <span className="min-w-0 truncate">{page.title}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {page.duration_minutes} min
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}
