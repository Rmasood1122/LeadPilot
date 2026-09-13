"use client";

/** Feature A5 — this lead's live conversion probability, the evidence behind
 *  it, and the state the system put them in (cooling pauses the sequence,
 *  archived stops it). A person can override with Reactivate. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { TrendingDown } from "lucide-react";

import { getLeadConversion, reactivateLead } from "@/lib/api/conversion";
import {
  describeFactor,
  killSignalText,
  probabilityPercent,
  stateTone,
} from "@/lib/conversionProbability";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ConversionCard({ leadId }: { leadId: string }) {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["lead", leadId, "conversion"],
                           queryFn: () => getLeadConversion(leadId) });
  const reactivate = useMutation({
    mutationFn: () => reactivateLead(leadId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["lead", leadId] }),
  });
  const data = query.data;
  const state = data?.stored.engagement_state ?? "active";
  const lines = (data?.live.factors ?? []).map(describeFactor).filter(Boolean) as string[];

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2">
          <TrendingDown size={16} aria-hidden="true" /> Conversion probability
        </CardTitle>
        <Badge tone={stateTone(state)}>{state}</Badge>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {query.isLoading && <p className="text-muted-foreground">Estimating…</p>}
        {data && (
          <>
            <p className="text-3xl font-bold tabular-nums">{probabilityPercent(data.live.probability)}</p>
            {data.live.kill_signal && (
              <p className="text-destructive">Stopped because {killSignalText(data.live.kill_signal)}.</p>
            )}
            {lines.length > 0 && (
              <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
                {lines.map((line) => <li key={line}>{line}</li>)}
              </ul>
            )}
            {(state === "cooling" || state === "archived") && (
              <div className="space-y-1">
                <Button size="sm" variant="outline" disabled={reactivate.isPending}
                        onClick={() => reactivate.mutate()}>
                  Reactivate lead
                </Button>
                <p className="text-xs text-muted-foreground">
                  {state === "cooling"
                    ? "Resumes the paused sequence now."
                    : "Clears the archive. Stopped sequences stay stopped — re-enroll to contact again."}
                </p>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
