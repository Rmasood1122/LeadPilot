"use client";

/** Part 1 Feature 3 — did enrolled prospects receive the whole sequence?
 *
 *  The completion rate on its own is not a verdict: 60% is fine if the other
 *  40% replied, and alarming if the system dropped them. So the panel always
 *  splits the reasons into DECISIONS (a reply, an unsubscribe, a bounce, a
 *  booking, a suppression, a human closing them in the CRM) and DROPS
 *  (an automated kill signal, every step skipped, a reason nothing
 *  recognises) — and only the second group raises a warning. */

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import {
  getDroppedProspects,
  getStrategyCompletion,
} from "@/lib/api/sequenceCompletion";
import {
  completionCaption,
  groupedReasons,
  guaranteeWarning,
  percent,
  worstSequences,
} from "@/lib/sequenceCompletion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";

export function CompletionPanel({ strategyId }: { strategyId?: string }) {
  const [showDropped, setShowDropped] = useState(false);
  const { data, isLoading, error } = useQuery({
    queryKey: ["sequence-completion", strategyId ?? ""],
    queryFn: () => getStrategyCompletion(strategyId as string),
    enabled: Boolean(strategyId),
  });
  const dropped = useQuery({
    queryKey: ["sequence-dropped", strategyId ?? ""],
    queryFn: () => getDroppedProspects(strategyId as string, true),
    enabled: Boolean(strategyId) && showDropped,
  });

  if (!strategyId) return null;
  const { decisions, drops } = groupedReasons(data);
  const warning = guaranteeWarning(data);
  const worst = worstSequences(data?.by_sequence ?? []);

  return (
    <Card aria-label="Sequence completion">
      <CardHeader>
        <CardTitle className="text-sm">Sequence completion</CardTitle>
        <p className="text-xs text-muted-foreground">{completionCaption(data)}</p>
      </CardHeader>
      <CardContent>
        <AsyncState isLoading={isLoading} error={error}
                    empty={!!data && data.enrolled === 0}
                    emptyLabel="Nobody enrolled yet.">
          {data && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-6">
                <div>
                  <p className="text-xs text-muted-foreground">Completion rate</p>
                  <p className="text-2xl font-semibold">{percent(data.completion_rate)}</p>
                  <p className="text-xs text-muted-foreground">
                    {data.completed} ran to the end
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Stopped early</p>
                  <p className="text-2xl font-semibold">{data.dropped}</p>
                  <p className="text-xs text-muted-foreground">
                    {data.dropped - data.dropped_unauthorised} by decision
                  </p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Still running</p>
                  <p className="text-2xl font-semibold">{data.running}</p>
                  <p className="text-xs text-muted-foreground">not counted either way</p>
                </div>
              </div>

              {warning && (
                <p className="flex items-start gap-2 text-sm font-medium">
                  <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
                  {warning}
                </p>
              )}

              {decisions.length > 0 && (
                <ReasonList title="Stopped by a decision" rows={decisions} tone="default" />
              )}
              {drops.length > 0 && (
                <ReasonList title="Stopped without a decision" rows={drops} tone="destructive" />
              )}

              {worst.length > 1 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Lowest completion by sequence
                  </p>
                  <ul className="mt-1 space-y-0.5 text-sm">
                    {worst.map((row) => (
                      <li key={row.sequence_id} className="flex justify-between gap-2">
                        <span className="truncate">{row.name}</span>
                        <span className="tabular-nums text-muted-foreground">
                          {percent(row.completion_rate)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {data.dropped_unauthorised > 0 && (
                <div>
                  <Button size="sm" variant="ghost"
                          onClick={() => setShowDropped((open) => !open)}>
                    {showDropped ? "Hide" : "Show"} the {data.dropped_unauthorised} to check
                  </Button>
                  {showDropped && (
                    <AsyncState isLoading={dropped.isLoading} error={dropped.error}
                                empty={!dropped.data?.items.length}
                                emptyLabel="Nothing to check.">
                      <ul className="mt-2 space-y-1 text-sm">
                        {dropped.data?.items.map((row) => (
                          <li key={row.enrollment_id} className="flex flex-wrap gap-2">
                            <Link href={`/leads/detail?id=${row.lead.id}`}
                                  className="font-medium hover:underline">
                              {row.lead.full_name ?? row.lead.email ?? row.lead.id}
                            </Link>
                            <span className="text-muted-foreground">
                              step {row.steps_sent} of {row.planned_steps ?? "?"}
                            </span>
                            <Badge tone="destructive">{row.stop_label ?? row.stop_reason}</Badge>
                          </li>
                        ))}
                      </ul>
                    </AsyncState>
                  )}
                </div>
              )}

              {data.unknown > 0 && (
                <p className="text-xs text-muted-foreground">
                  {data.unknown} enrollment{data.unknown === 1 ? " was" : "s were"} created
                  before completion was tracked, so {data.unknown === 1 ? "it is" : "they are"}{" "}
                  counted as unknown rather than as a failure.
                </p>
              )}
            </div>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}

function ReasonList({ title, rows, tone }: {
  title: string;
  rows: { category: string; label: string; count: number }[];
  tone: "default" | "destructive";
}) {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <ul className="mt-1 space-y-1" aria-label={title}>
        {rows.map((row) => (
          <li key={row.category} className="flex items-center gap-2 text-sm">
            <Badge tone={tone}>{row.label}</Badge>
            <span className="text-muted-foreground tabular-nums">{row.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
