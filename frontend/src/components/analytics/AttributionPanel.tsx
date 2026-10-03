"use client";

/** Part 1 Feature 8 — which touch earned each outcome.
 *
 *  The panel's job is to be honest about the difference between a fact and a
 *  guess. "They replied to step 2" is known. "Step 2 was the last thing we
 *  sent before they booked three weeks later" is an inference, and every
 *  outbound tool that presents those identically ends up with users building
 *  a sequence strategy on coincidence.
 *
 *  So: every row states its method and confidence, and an aggregate built
 *  mostly from guesses carries a caveat above it. */

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw } from "lucide-react";

import {
  getAttributionSummary,
  listAttribution,
  recomputeAttribution,
} from "@/lib/api/attribution";
import {
  certaintyNote,
  gapLabel,
  methodTone,
  outcomeLabel,
  rankedSteps,
  summaryCaveat,
  touchLabel,
  type AttributionEntry,
} from "@/lib/attribution";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function AttributionPanel({ strategyId }: { strategyId?: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(false);

  const summary = useQuery({
    queryKey: ["attribution-summary", strategyId ?? ""],
    queryFn: () => getAttributionSummary(strategyId),
  });
  const entries = useQuery({
    queryKey: ["attribution", strategyId ?? "", expanded],
    queryFn: () => listAttribution({ strategyId, limit: expanded ? 50 : 5 }),
  });
  const recompute = useMutation({
    mutationFn: recomputeAttribution,
    onSuccess: (result) => {
      qc.invalidateQueries({ queryKey: ["attribution"] });
      qc.invalidateQueries({ queryKey: ["attribution-summary"] });
      toast(`${result.recorded} newly credited`, "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const caveat = summaryCaveat(summary.data);
  const steps = rankedSteps(summary.data);

  return (
    <Card aria-label="Attribution">
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle className="text-sm">What earned the outcomes</CardTitle>
          {summary.data && (
            <p className="text-xs text-muted-foreground">
              {summary.data.total} credited · {summary.data.certain} confirmed by a reply
              {summary.data.median_hours_to_outcome !== null
                && ` · typically ${gapLabel(summary.data.median_hours_to_outcome)}`}
            </p>
          )}
        </div>
        <Button size="sm" variant="ghost" disabled={recompute.isPending}
                onClick={() => recompute.mutate()}>
          <RefreshCw size={14} aria-hidden="true" />
          {recompute.isPending ? "Working…" : "Recompute"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <AsyncState isLoading={summary.isLoading} error={summary.error}
                    empty={!!summary.data && summary.data.total === 0}
                    emptyLabel="No booked meetings or positive replies yet.">
          {caveat && (
            <p className="flex items-start gap-2 text-sm">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
              {caveat}
            </p>
          )}

          {steps.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">By step</p>
              <ul className="mt-1 space-y-1 text-sm">
                {steps.map((row) => (
                  <li key={row.step_no} className="flex justify-between gap-2">
                    <span>Step {row.step_no}</span>
                    <span className="tabular-nums text-muted-foreground">
                      {row.count} ({row.certain} confirmed)
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {summary.data && summary.data.by_channel.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">By channel</p>
              <ul className="mt-1 space-y-1 text-sm">
                {summary.data.by_channel.map((row) => (
                  <li key={row.channel} className="flex justify-between gap-2">
                    <span className="capitalize">{row.channel}</span>
                    <span className="tabular-nums text-muted-foreground">
                      {row.count} ({row.certain} confirmed)
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </AsyncState>

        <AsyncState isLoading={entries.isLoading} error={entries.error}
                    empty={!entries.data?.items.length} emptyLabel="">
          <ul className="space-y-2">
            {entries.data?.items.map((entry) => (
              <EntryRow key={entry.id} entry={entry} />
            ))}
          </ul>
          {entries.data && entries.data.total > entries.data.items.length && (
            <Button size="sm" variant="ghost" onClick={() => setExpanded(true)}>
              Show all {entries.data.total}
            </Button>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}

function EntryRow({ entry }: { entry: AttributionEntry }) {
  return (
    <li className="space-y-1 border-b border-border/40 pb-2 text-sm last:border-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="default">{outcomeLabel(entry.outcome_kind)}</Badge>
        {entry.lead && (
          <Link href={`/leads/detail?id=${entry.lead.id}`}
                className="font-medium hover:underline">
            {entry.lead.full_name ?? entry.lead.company ?? "Prospect"}
          </Link>
        )}
        <Badge tone={methodTone(entry.method)}>{touchLabel(entry)}</Badge>
        <span className="text-xs text-muted-foreground">
          {gapLabel(entry.hours_to_outcome)}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{certaintyNote(entry)}</p>
      {entry.subject && <p className="text-xs">“{entry.subject}”</p>}
    </li>
  );
}
