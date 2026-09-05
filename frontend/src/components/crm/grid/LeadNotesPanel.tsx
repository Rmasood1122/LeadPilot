"use client";

/** Notes and activity for one lead, opened from the grid's notes cell.
 *
 * Uses the existing Modal primitive rather than a bespoke drawer — the app
 * already has one, it already traps focus and handles Escape, and a second
 * overlay implementation is a second set of accessibility bugs.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import { getLeadActivity } from "@/lib/api/crm";
import { useCreateNote, useCrmNotes, useDeleteNote } from "@/lib/api/crm-hooks";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";

export function LeadNotesPanel({
  leadId,
  onClose,
}: {
  leadId: string;
  onClose: () => void;
}) {
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
    <Modal open onClose={onClose} title="Notes & activity">
      <div className="space-y-4 text-sm">
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
    </Modal>
  );
}
