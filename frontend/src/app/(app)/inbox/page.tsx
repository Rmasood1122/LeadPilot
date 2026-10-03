"use client";

/** Part 1 Feature 6 — the unified cross-channel inbox: `/inbox?lead=<id>`.
 *
 *  THREADED BY PERSON, NOT BY CHANNEL. A prospect who answered an email on
 *  Tuesday and replied on LinkedIn on Thursday is one conversation. Filing
 *  those as two inboxes makes someone rebuild the relationship in their head
 *  before they can answer, and the usual result is a reply that contradicts
 *  something said on another channel two days earlier.
 *
 *  "Needs reply" is worked OLDEST first (the API orders it), so the replies
 *  that have waited longest are at the top rather than buried under today's.
 *
 *  ROUTE SHAPE: a query parameter rather than /inbox/[id], for the same reason
 *  as every other detail page here — next.config.js sets `output: 'export'`,
 *  so a dynamic segment cannot serve an id that did not exist at build time. */

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Inbox as InboxIcon, RotateCcw } from "lucide-react";

import { getInboxThread, listInbox, setThreadHandled } from "@/lib/api/inbox";
import {
  channelSummary,
  emptyLabel,
  isOverdue,
  latestBadge,
  relativeTime,
  threadName,
  threadSubtitle,
  type InboxFilter,
  type InboxThread,
} from "@/lib/inbox";
import { ConversationThread } from "@/components/leads/ConversationThread";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const FILTERS: { value: InboxFilter; label: string }[] = [
  { value: "needs_reply", label: "Needs reply" },
  { value: "all", label: "All" },
  { value: "handled", label: "Cleared" },
];

export default function InboxPage() {
  return (
    <Suspense fallback={null}>
      <InboxView />
    </Suspense>
  );
}

function InboxView() {
  const params = useSearchParams();
  const router = useRouter();
  const selected = params.get("lead");
  const [filter, setFilter] = useState<InboxFilter>("needs_reply");

  const query = useQuery({
    queryKey: ["inbox", filter],
    queryFn: () => listInbox({ filter }),
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <InboxIcon size={20} aria-hidden="true" /> Inbox
        </h1>
        <div className="flex flex-wrap gap-2">
          {FILTERS.map((option) => (
            <Button key={option.value} size="sm"
                    variant={filter === option.value ? "default" : "ghost"}
                    onClick={() => setFilter(option.value)}>
              {option.label}
              {option.value === "needs_reply" && query.data?.needs_reply_total
                ? ` (${query.data.needs_reply_total})` : ""}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
        <div>
          <AsyncState isLoading={query.isLoading} error={query.error}
                      empty={!query.data?.items.length}
                      emptyLabel={emptyLabel(filter)}>
            <ul className="space-y-2">
              {query.data?.items.map((thread) => (
                <ThreadRow key={thread.lead.id} thread={thread}
                           active={selected === thread.lead.id}
                           onOpen={() => router.replace(`/inbox?lead=${thread.lead.id}`)} />
              ))}
            </ul>
          </AsyncState>
        </div>

        <div>
          {selected
            ? <ThreadDetail leadId={selected} filter={filter} />
            : <Card><CardContent className="p-gutter text-sm text-muted-foreground">
                Pick a conversation to read the whole thread — every channel, in order.
              </CardContent></Card>}
        </div>
      </div>
    </div>
  );
}

function ThreadRow({ thread, active, onOpen }: {
  thread: InboxThread; active: boolean; onOpen: () => void;
}) {
  const badge = latestBadge(thread);
  const overdue = isOverdue(thread);

  return (
    <li>
      <button type="button" onClick={onOpen}
              className={cn(
                "w-full rounded border border-border p-3 text-left text-sm",
                active ? "border-[rgb(var(--primary))] bg-card" : "bg-card/50 hover:bg-card",
              )}>
        <div className="flex items-start justify-between gap-2">
          <span className="truncate font-medium">{threadName(thread)}</span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {relativeTime(thread.last_inbound_at)}
          </span>
        </div>
        <p className="truncate text-xs text-muted-foreground">{threadSubtitle(thread)}</p>
        {thread.latest && (
          <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
            {thread.latest.preview}
          </p>
        )}
        <div className="mt-1 flex flex-wrap items-center gap-1">
          <Badge tone="default">{channelSummary(thread)}</Badge>
          {badge && <Badge tone={badge.tone}>{badge.text}</Badge>}
          {thread.unhandled_count > 1 && (
            <Badge tone="default">{thread.unhandled_count} waiting</Badge>
          )}
          {overdue && <Badge tone="warning">Overdue</Badge>}
        </div>
      </button>
    </li>
  );
}

function ThreadDetail({ leadId, filter }: { leadId: string; filter: InboxFilter }) {
  const toast = useToast();
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["inbox-thread", leadId],
    queryFn: () => getInboxThread(leadId),
  });
  const handled = useMutation({
    mutationFn: (next: boolean) => setThreadHandled(leadId, next),
    onSuccess: (_result, next) => {
      qc.invalidateQueries({ queryKey: ["inbox"] });
      qc.invalidateQueries({ queryKey: ["inbox-thread", leadId] });
      toast(next ? "Cleared from the inbox" : "Back in the inbox", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const thread = data?.inbox;

  return (
    <div className="space-y-3">
      <AsyncState isLoading={isLoading} error={error}>
        {thread && (
          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-2 p-gutter">
              <div className="min-w-0">
                <Link href={`/leads/detail?id=${leadId}`}
                      className="font-medium hover:underline">
                  {threadName(thread)}
                </Link>
                <p className="text-xs text-muted-foreground">
                  {[threadSubtitle(thread), channelSummary(thread),
                    `${thread.reply_count} inbound`].filter(Boolean).join(" · ")}
                </p>
              </div>
              {thread.needs_reply ? (
                <Button size="sm" disabled={handled.isPending}
                        onClick={() => handled.mutate(true)}>
                  <Check size={16} aria-hidden="true" /> Mark handled
                </Button>
              ) : (
                <Button size="sm" variant="ghost" disabled={handled.isPending}
                        onClick={() => handled.mutate(false)}>
                  <RotateCcw size={16} aria-hidden="true" /> Put back
                </Button>
              )}
            </CardContent>
          </Card>
        )}
      </AsyncState>

      {/* The same timeline the lead page shows — one implementation, so the
          two views can never disagree about a prospect's history. */}
      <ConversationThread leadId={leadId} />
      <p className="text-xs text-muted-foreground">
        Marking a thread handled sends nothing. It records that a person has
        dealt with it — including when the answer went out from somewhere else.
        {filter === "handled" && " Cleared threads stay here; put one back to work it again."}
      </p>
    </div>
  );
}
