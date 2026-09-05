"use client";

/** CRM dashboard — page 4: the account activity feed.
 *
 * A real-time timeline of everything that happened to a lead: created, moved
 * between stages, tagged, noted, replied, booked. Filterable by strategy and
 * by event kind.
 *
 * The feed is where the SSE stream is most visible — new entries appear
 * without a refresh, because CrmRealtimeContext invalidates the
 * ["crm-activity"] key on every activity.created and lead.status_changed
 * event. When the stream is down, the 60-second poll keeps it moving and the
 * indicator in the header says "Polling" rather than "Live".
 */

import { useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  CircleDot,
  MessageSquare,
  Tag as TagIcon,
  UserPlus,
} from "lucide-react";

import { useCrmActivity } from "@/lib/api/crm-hooks";
import { StrategyScope } from "@/components/crm/CrmChrome";
import { SectionHeading, stageLabel } from "@/components/crm/dashboard/primitives";
import { AsyncState } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { CrmActivityItem, CrmActivityKind } from "@/lib/api/types";

const KIND_FILTERS: { value: CrmActivityKind | "all"; label: string }[] = [
  { value: "all", label: "Everything" },
  { value: "status_changed", label: "Stage changes" },
  { value: "note_added", label: "Notes" },
  { value: "tag_added", label: "Tags" },
  { value: "meeting_booked", label: "Meetings" },
  { value: "reply_received", label: "Replies" },
];

function iconFor(kind: CrmActivityKind) {
  switch (kind) {
    case "note_added":
    case "note_deleted":
      return MessageSquare;
    case "tag_added":
    case "tag_removed":
      return TagIcon;
    case "meeting_booked":
      return CheckCircle2;
    case "lead_created":
      return UserPlus;
    case "status_changed":
      return ArrowRight;
    default:
      return CircleDot;
  }
}

/** A short sentence describing what happened, in the past tense. */
function describe(item: CrmActivityItem): React.ReactNode {
  switch (item.kind) {
    case "status_changed":
      return (
        <>
          moved from{" "}
          <span className="font-medium">{stageLabel(item.from_value ?? "?")}</span>{" "}
          to <span className="font-medium">{stageLabel(item.to_value ?? "?")}</span>
        </>
      );
    case "note_added":
      return (
        <>
          note added: <span className="italic">{item.to_value}</span>
        </>
      );
    case "note_deleted":
      return "note deleted";
    case "tag_added":
      return (
        <>
          tagged <span className="font-medium">{item.to_value}</span>
        </>
      );
    case "tag_removed":
      return (
        <>
          untagged <span className="font-medium">{item.from_value}</span>
        </>
      );
    case "owner_changed":
      return item.to_value ? "owner assigned" : "owner cleared";
    case "field_changed": {
      const field = (item.meta?.field as string) ?? "field";
      return (
        <>
          <span className="font-medium">{field}</span> set to{" "}
          <span className="font-medium">{item.to_value ?? "empty"}</span>
        </>
      );
    }
    case "meeting_booked":
      return "booked a meeting";
    case "reply_received":
      return "replied";
    case "lead_created":
      return "was added to the pipeline";
    default:
      // Unreachable for every kind the client knows about -- which is exactly
      // why it stays: the backend's CrmActivityKind is a VARCHAR-backed enum,
      // so a new kind can ship server-side before this file learns about it,
      // and the feed should render it plainly rather than blank the row.
      return String(item.kind).replace(/_/g, " ");
  }
}

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export default function CrmActivityPage() {
  const [strategyId, setStrategyId] = useState("");
  const [kind, setKind] = useState<CrmActivityKind | "all">("all");

  const { data, isLoading, error } = useCrmActivity({
    strategyId: strategyId || null,
    kinds: kind === "all" ? undefined : [kind],
    limit: 100,
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionHeading
          title="Activity"
          hint="Everything that happened across the account, newest first."
        />
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="sr-only">Event type</span>
            <select
              className="rounded border border-border bg-card px-2 py-1 text-sm text-foreground"
              value={kind}
              onChange={(event) =>
                setKind(event.target.value as CrmActivityKind | "all")
              }
              aria-label="Event type"
            >
              {KIND_FILTERS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <StrategyScope value={strategyId} onChange={setStrategyId} />
        </div>
      </div>

      <AsyncState
        isLoading={isLoading}
        error={error}
        empty={items.length === 0}
        emptyLabel="No activity yet. Working a lead — moving it, tagging it, adding a note — shows up here."
      >
        <Card>
          <CardContent className="p-0">
            <ol className="divide-y divide-border">
              {items.map((item) => {
                const Icon = iconFor(item.kind);
                const who =
                  item.lead.full_name ?? item.lead.company ?? item.lead.email ?? "A lead";
                return (
                  <li key={item.id} className="flex items-start gap-3 p-3">
                    <span
                      className={cn(
                        "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full",
                        item.kind === "meeting_booked"
                          ? "bg-[rgb(var(--success))]/15 text-[rgb(var(--success))]"
                          : "bg-muted text-muted-foreground",
                      )}
                      aria-hidden="true"
                    >
                      <Icon size={13} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm">
                        <span className="font-medium">{who}</span>{" "}
                        <span className="text-muted-foreground">{describe(item)}</span>
                      </p>
                      <p className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                        <span title={item.ts ?? undefined}>{relativeTime(item.ts)}</span>
                        {item.lead.company && (
                          <span className="truncate">· {item.lead.company}</span>
                        )}
                        {/* A NULL actor means the pipeline did it, not a
                            person — worth distinguishing, because "you moved
                            this" and "the system moved this" call for
                            different follow-up. */}
                        {item.actor_user_id === null && (
                          <Badge tone="default" title="Recorded by the pipeline, not by a person">
                            automated
                          </Badge>
                        )}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ol>
          </CardContent>
        </Card>

        {data?.has_more && (
          <p className="text-center text-xs text-muted-foreground">
            Showing the {items.length} most recent events.
          </p>
        )}
      </AsyncState>
    </div>
  );
}
