"use client";

/** Part 1 Feature 12 — "Why this prospect", built entirely from Feature 2's
 *  F-P-T-A signals.
 *
 *  The rule the panel exists to enforce: every claim is traceable. The
 *  headline names the dimension that drove the score, each row shows the
 *  reason AND the raw evidence it was written from, and a dimension with no
 *  evidence says "no visible signal" rather than borrowing confidence from a
 *  neighbour. Nothing here is generated prose over an unexplained number.
 *
 *  It also says out loud when the reasons came from the deterministic
 *  fallback rather than the model, so terse wording is never mistaken for a
 *  weak prospect. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import { getLeadFpta, rescoreLeadFpta } from "@/lib/api/fpta";
import {
  band,
  bandLabel,
  bandTone,
  dimensionName,
  dimensionQuestion,
  explanationRows,
  isHeuristicOnly,
  scoreText,
  whyAdvice,
  whyHeadline,
} from "@/lib/fpta";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function WhyThisProspectPanel({ leadId }: { leadId: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["lead-fpta", leadId],
    queryFn: () => getLeadFpta(leadId),
  });
  const rescore = useMutation({
    mutationFn: () => rescoreLeadFpta(leadId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead-fpta", leadId] });
      qc.invalidateQueries({ queryKey: ["lead", leadId] });
      toast("F-P-T-A updated", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const advice = whyAdvice(data);

  return (
    <Card className="lg:col-span-2" aria-label="Why this prospect">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle>Why this prospect</CardTitle>
        <div className="flex items-center gap-2">
          {data && (
            <Badge tone={bandTone(data.band)} className="tabular-nums">
              {scoreText(data.overall)} · {bandLabel(data.band)}
            </Badge>
          )}
          <Button size="sm" variant="ghost" disabled={rescore.isPending}
                  onClick={() => rescore.mutate()}>
            <RefreshCw size={14} aria-hidden="true" />
            {rescore.isPending ? "Scoring…" : "Rescore"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <AsyncState isLoading={isLoading} error={error}>
          {data && (
            <>
              <p>{whyHeadline(data)}</p>
              {advice && <p className="font-medium">{advice}</p>}
              {data.engagement && (
                <p className="text-xs text-muted-foreground">So far: {data.engagement}</p>
              )}

              <ul className="space-y-3">
                {explanationRows(data).map((row) => (
                  <li key={row.key} className="space-y-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-medium" title={dimensionQuestion(row.key)}>
                        {dimensionName(row.key)}
                      </span>
                      <Badge tone={bandTone(band(row.score))} className="tabular-nums">
                        {scoreText(row.score)}
                      </Badge>
                    </div>
                    <div className="h-1.5 rounded bg-muted" aria-hidden="true">
                      <div className="h-1.5 rounded bg-[rgb(var(--primary))]"
                           style={{ width: `${row.score ?? 0}%` }} />
                    </div>
                    {row.reason && <p className="text-muted-foreground">{row.reason}</p>}
                    {row.signals.length > 0 && (
                      <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                        {row.signals.map((signal) => <li key={signal}>{signal}</li>)}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>

              <p className="text-xs text-muted-foreground">
                Weighted: fit {Math.round((data.weights?.fit ?? 0) * 100)}%, problem{" "}
                {Math.round((data.weights?.problem ?? 0) * 100)}%, timing{" "}
                {Math.round((data.weights?.timing ?? 0) * 100)}%, access{" "}
                {Math.round((data.weights?.access ?? 0) * 100)}%.
                {isHeuristicOnly(data) && (
                  <> The AI pass was unavailable, so these reasons are the raw
                  evidence rather than written explanations.</>
                )}
              </p>
            </>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}
