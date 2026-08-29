"use client";

/**
 * Admin — the support ticket queue (Feature 3).
 *
 * Open tickets first, oldest first, because the queue is worked from the front
 * and the oldest unanswered ticket is the one closest to breaking the
 * 24-hour promise the chat widget makes to users.
 *
 * Tickets are NOT emailed anywhere — email delivery is deferred with the rest
 * of the transport work — so this page is currently the only place they can be
 * seen. That makes "is anybody watching this queue?" an operational question,
 * not a UI one; the open count is shown prominently for that reason.
 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api/admin";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

export default function AdminSupportTicketsPage() {
  const [statusFilter, setStatusFilter] = useState<"open" | "resolved" | "">("open");
  const [resolving, setResolving] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const qc = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "support-tickets", statusFilter],
    queryFn: () => adminApi.listSupportTickets(statusFilter || undefined),
  });

  const resolve = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      adminApi.resolveSupportTicket(id, text),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "support-tickets"] });
      setResolving(null);
      setNote("");
    },
  });

  const tickets = data?.tickets ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Support Tickets</h1>
          <p className="text-sm text-muted-foreground">
            Raised from the in-app AI chat when it could not answer.
            Tickets are stored here only — they are not emailed anywhere yet.
          </p>
        </div>
        <div className="shrink-0 rounded border border-border px-4 py-2 text-center">
          <p className="text-xs text-muted-foreground">Open</p>
          <p data-testid="open-ticket-count" className="text-2xl font-semibold">
            {data?.open_count ?? 0}
          </p>
        </div>
      </div>

      <div className="flex gap-2" role="group" aria-label="Filter by status">
        {([["open", "Open"], ["resolved", "Resolved"], ["", "All"]] as const).map(
          ([value, label]) => (
            <Button
              key={label}
              type="button"
              size="sm"
              variant={statusFilter === value ? "default" : "outline"}
              aria-pressed={statusFilter === value}
              onClick={() => setStatusFilter(value)}
            >
              {label}
            </Button>
          ),
        )}
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading…</div>
      ) : error ? (
        <div role="alert" className="rounded border border-destructive/40 p-4 text-sm">
          Could not load tickets.
        </div>
      ) : tickets.length === 0 ? (
        <div className="rounded border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          No {statusFilter || ""} tickets.
        </div>
      ) : (
        <ul className="space-y-3">
          {tickets.map((ticket) => (
            <li
              key={ticket.id}
              data-testid={`ticket-${ticket.id}`}
              className="rounded border border-border p-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">{ticket.subject}</p>
                  <p className="text-xs text-muted-foreground">
                    {ticket.user_email ?? ticket.user_id} ·{" "}
                    {ticket.created_at
                      ? new Date(ticket.created_at).toLocaleString()
                      : "—"}
                  </p>
                </div>
                <Badge tone={ticket.status === "open" ? "warning" : "success"}>
                  {ticket.status}
                </Badge>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm">{ticket.body}</p>
              {ticket.resolution_note && (
                <p className="mt-2 rounded bg-muted p-2 text-xs">
                  <span className="font-medium">Resolution: </span>
                  {ticket.resolution_note}
                </p>
              )}
              {ticket.status === "open" && (
                <Button
                  type="button"
                  size="sm"
                  className="mt-3"
                  onClick={() => setResolving(ticket.id)}
                >
                  Mark resolved
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <Dialog open={!!resolving} onOpenChange={(o) => !o && setResolving(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Resolve ticket</DialogTitle>
          </DialogHeader>
          <Textarea
            rows={4}
            placeholder="What was done? (optional, visible to the user)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setResolving(null)}>
              Cancel
            </Button>
            <Button
              onClick={() =>
                resolving && resolve.mutate({ id: resolving, text: note })
              }
              disabled={resolve.isPending}
            >
              {resolve.isPending ? "Saving…" : "Resolve"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
