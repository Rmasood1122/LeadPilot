"use client";

/** F02 Signal Radar — "why now", with the source one click away.
 *
 *  Every signal shows its age next to its source, because a funding round
 *  from last week and one from last spring are different reasons to write.
 *  Each non-citable signal says why it will not be used in a message (no
 *  public link, expired, ...). Renders nothing when the feature is off. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Radar, RefreshCw } from "lucide-react";

import { getLeadSignals, refreshLeadSignals } from "@/lib/api/signals";
import {
  ageLabel,
  orderSignals,
  safeHref,
  signalHeadline,
  sourceText,
  statusLabel,
  statusTone,
  type LeadSignal,
} from "@/lib/signals";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function SignalRadarPanel({ leadId }: { leadId: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["lead-signals", leadId],
    queryFn: () => getLeadSignals(leadId),
  });
  const refresh = useMutation({
    mutationFn: () => refreshLeadSignals(leadId),
    onSuccess: (fresh) => {
      qc.setQueryData(["lead-signals", leadId], fresh);
      toast("Signals refreshed from stored data", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  if (data && !data.enabled) return null;

  return (
    <Card aria-label="Why now — signals">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Radar size={16} aria-hidden="true" /> Why now
        </CardTitle>
        <Button size="sm" variant="ghost" disabled={refresh.isPending}
                onClick={() => refresh.mutate()}>
          <RefreshCw size={14} aria-hidden="true" />
          {refresh.isPending ? "Refreshing…" : "Refresh"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <AsyncState isLoading={isLoading} error={error}>
          {data && (
            <>
              <p className="text-xs text-muted-foreground">{signalHeadline(data)}</p>
              <ul className="space-y-3">
                {orderSignals(data.signals).map((s) => <SignalRow key={s.id} signal={s} />)}
              </ul>
            </>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}

function SignalRow({ signal }: { signal: LeadSignal }) {
  const href = safeHref(signal.source_url);
  return (
    <li className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={statusTone(signal.status)}>{statusLabel(signal.status)}</Badge>
        <span className="font-medium">{signal.type_label}</span>
        <span className="text-xs text-muted-foreground">{ageLabel(signal.age_days)}</span>
      </div>
      <p className="break-words">{signal.title}</p>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {href ? (
          <a href={href} target="_blank" rel="noopener noreferrer"
             className="inline-flex items-center gap-1 underline">
            {sourceText(signal)} <ExternalLink size={12} aria-hidden="true" />
          </a>
        ) : (
          <span>{sourceText(signal)} · no public link</span>
        )}
        <span>· {Math.round(signal.confidence * 100)}% source confidence</span>
        {!signal.citable && signal.not_citable_reason && (
          <Badge tone="default">Not cited: {signal.not_citable_reason}</Badge>
        )}
      </div>
    </li>
  );
}
