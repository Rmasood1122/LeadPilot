"use client";

/** Every "Log Meeting Outcome" submission for a lead, newest first, each with
 *  the follow-up it produced. A second submission is a new row, not an edit --
 *  the history is how "it went well, then the deal fell through" stays
 *  readable. */

import { useQuery } from "@tanstack/react-query";

import { listMeetingOutcomes } from "@/lib/api/meetingPrep";
import { outcomeLabel } from "@/lib/meeting-prep";
import { Badge, statusTone } from "@/components/ui/badge";
import { AsyncState } from "@/components/ui/skeleton";
import { FollowupDraftCard } from "./FollowupDraftCard";

export function OutcomeHistory({ leadId }: { leadId: string }) {
  const query = useQuery({
    queryKey: ["meeting-outcomes", leadId],
    queryFn: () => listMeetingOutcomes(leadId),
  });
  const rows = query.data ?? [];

  return (
    <AsyncState
      isLoading={query.isLoading}
      error={query.error}
      empty={rows.length === 0}
      emptyLabel="No meeting outcomes logged yet. Use “Log Meeting Outcome” after the call."
    >
      <ol className="space-y-4">
        {rows.map((row) => (
          <li key={row.id} className="space-y-3 rounded-lg border border-border bg-card p-4 text-sm">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(row.new_status ?? "")}>{outcomeLabel(row.outcome)}</Badge>
              <span className="text-muted-foreground">
                {new Date(row.created_at).toLocaleString()}
              </span>
              <span className="font-mono text-xs text-muted-foreground">
                {row.previous_status ?? "—"} → {row.new_status}
              </span>
              {row.deal_id && <Badge tone="success">Deal created</Badge>}
            </div>
            {row.notes && <p className="whitespace-pre-wrap">{row.notes}</p>}
            {row.draft_status !== "pending" && <FollowupDraftCard outcome={row} />}
          </li>
        ))}
      </ol>
    </AsyncState>
  );
}
