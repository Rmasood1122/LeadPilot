"use client";

/** Feature A4 — one chronological conversation across email, LinkedIn,
 *  WhatsApp, calls and meetings, with the stagnation step's channel-switch
 *  suggestion on top when the lead has gone quiet. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRightLeft, Calendar, Linkedin, Mail, MessageCircle, Phone, Video } from "lucide-react";

import {
  acceptSuggestion,
  dismissSuggestion,
  getConversation,
  getLeadSuggestions,
} from "@/lib/api/conversations";
import {
  channelLabel,
  dayLabel,
  formatDuration,
  groupByDay,
  itemTitle,
  openSuggestions,
  type ThreadItem,
} from "@/lib/conversation";
import { kindLabel, kindTone } from "@/lib/authenticity";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const ICONS: Record<string, typeof Mail> = {
  email: Mail, linkedin: Linkedin, whatsapp: MessageCircle, phone: Phone,
  calendar: Calendar, meeting: Video,
};

export function ConversationThread({ leadId }: { leadId: string }) {
  const qc = useQueryClient();
  const thread = useQuery({ queryKey: ["lead", leadId, "conversation"],
                            queryFn: () => getConversation(leadId) });
  const suggestions = useQuery({ queryKey: ["lead", leadId, "channel-suggestions"],
                                 queryFn: () => getLeadSuggestions(leadId) });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["lead", leadId, "conversation"] });
    qc.invalidateQueries({ queryKey: ["lead", leadId, "channel-suggestions"] });
  };
  const accept = useMutation({ mutationFn: acceptSuggestion, onSuccess: refresh });
  const dismiss = useMutation({ mutationFn: dismissSuggestion, onSuccess: refresh });
  const open = openSuggestions(suggestions.data ?? []);

  return (
    <div className="space-y-4">
      {open.map((s) => (
        <Card key={s.id} className="border-[rgb(var(--warning))]">
          <CardContent className="flex flex-wrap items-center justify-between gap-3 p-gutter">
            <div className="flex items-start gap-2 text-sm">
              <ArrowRightLeft size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
              <div>
                <p className="font-medium">
                  Gone quiet on {channelLabel(s.from_channel)} — try {channelLabel(s.to_channel)}
                </p>
                <p className="text-xs text-muted-foreground">{s.reason}</p>
              </div>
            </div>
            <div className="flex gap-2">
              <Button size="sm" disabled={accept.isPending} onClick={() => accept.mutate(s.id)}>
                Switch next message
              </Button>
              <Button size="sm" variant="ghost" disabled={dismiss.isPending}
                      onClick={() => dismiss.mutate(s.id)}>
                Dismiss
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
      {accept.data?.note && <p className="text-xs text-muted-foreground">{accept.data.note}</p>}
      {accept.isError && (
        <p role="alert" className="text-sm text-destructive">{(accept.error as Error).message}</p>
      )}

      <AsyncState isLoading={thread.isLoading} error={thread.error}
                  empty={!thread.data?.items.length} emptyLabel="No conversation with this lead yet.">
        {thread.data && (
          <ol className="space-y-5">
            {groupByDay(thread.data.items).map((group) => (
              <li key={group.day}>
                <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {dayLabel(group.day)}
                </h3>
                <ul className="space-y-2">
                  {group.items.map((item) => <Entry key={item.id} item={item} />)}
                </ul>
              </li>
            ))}
          </ol>
        )}
      </AsyncState>
    </div>
  );
}

function Entry({ item }: { item: ThreadItem }) {
  const Icon = ICONS[item.channel] ?? ArrowRightLeft;
  const inbound = item.direction === "inbound";
  return (
    <li className={cn("flex", inbound ? "justify-end" : "justify-start")}>
      <div className={cn(
        "max-w-[85%] rounded-lg border p-3 text-sm",
        inbound ? "border-[rgb(var(--primary))] bg-muted" : "border-border bg-card",
        item.direction === "system" && "border-dashed",
        item.status === "scheduled" && "opacity-70",
      )}>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <Icon size={14} aria-hidden="true" />
          <span className="font-medium text-foreground">{itemTitle(item)}</span>
          {item.at && <span>{new Date(item.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>}
          {item.opened && <Badge tone="accent">opened{item.open_count && item.open_count > 1 ? ` ×${item.open_count}` : ""}</Badge>}
          {item.authenticity && (
            <Badge tone={kindTone(item.authenticity.kind as never)}>{kindLabel(item.authenticity.kind as never)}</Badge>
          )}
          {item.duration_seconds ? <span>{formatDuration(item.duration_seconds)}</span> : null}
        </div>
        {item.subject && <p className="mt-1 font-medium">{item.subject}</p>}
        {item.body && <p className="mt-1 whitespace-pre-line">{item.body}</p>}
      </div>
    </li>
  );
}
