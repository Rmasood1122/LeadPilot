"use client";

/** F01 — Waterfall Enrichment + Bounce Shield, per prospect.
 *
 *  Answers three questions: is this address verified (and who found it), will
 *  the next email actually go out (and if not, why), and what did finding it
 *  cost. The two actions are the only ways past a block: re-verify the
 *  address, or — for an owner or manager — allow sending anyway, with a
 *  reason that goes into the compliance audit log. An address verified
 *  undeliverable cannot be overridden; the button is not offered. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MailCheck, RefreshCw } from "lucide-react";

import {
  clearEmailOverride,
  getEmailVerdict,
  refreshEmailVerdict,
  setEmailOverride,
} from "@/lib/api/bounceShield";
import {
  attemptText,
  canOverride,
  canRefresh,
  panelVisible,
  sendDecisionText,
  totalCostUnits,
  verdictLabel,
  verdictTone,
  type EmailVerdict,
} from "@/lib/bounce-shield";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function EmailVerdictPanel({ leadId }: { leadId: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [reason, setReason] = useState("");
  const key = ["lead-email-verdict", leadId];

  const { data, isLoading, error } = useQuery({
    queryKey: key,
    queryFn: () => getEmailVerdict(leadId),
  });

  const onDone = (message: string) => (fresh: EmailVerdict) => {
    qc.setQueryData(key, fresh);
    const released = fresh.released_messages ?? 0;
    toast(released ? `${message} — ${released} held email(s) released` : message, "success");
  };
  const onError = (e: unknown) => toast((e as Error).message, "error");

  const refresh = useMutation({
    mutationFn: () => refreshEmailVerdict(leadId),
    onSuccess: onDone("Address re-verified"),
    onError,
  });
  const override = useMutation({
    mutationFn: () => setEmailOverride(leadId, reason.trim()),
    onSuccess: (fresh) => {
      setAsking(false);
      setReason("");
      onDone("Sending allowed for this prospect")(fresh);
    },
    onError,
  });
  const removeOverride = useMutation({
    mutationFn: () => clearEmailOverride(leadId),
    onSuccess: onDone("Override removed"),
    onError,
  });

  if (!isLoading && !error && !panelVisible(data)) return null;

  return (
    <Card aria-label="Email verification">
      <CardHeader className="gap-1">
        <CardTitle className="text-sm">Email verification</CardTitle>
        <p className="text-xs text-muted-foreground">{sendDecisionText(data)}</p>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <AsyncState isLoading={isLoading} error={error}>
          {data && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={verdictTone(data)}>{verdictLabel(data)}</Badge>
                {data.verdict?.provider && !data.verdict_is_stale_address && (
                  <span className="text-xs text-muted-foreground">
                    found by {data.verdict.provider}
                    {data.verdict.checked_at
                      ? ` · checked ${new Date(data.verdict.checked_at).toLocaleDateString()}`
                      : ""}
                  </span>
                )}
              </div>

              {data.override && (
                <div className="space-y-1 text-xs">
                  <p>
                    Sending allowed by override: “{data.override.reason}”
                    {" · "}{new Date(data.override.at).toLocaleDateString()}
                  </p>
                  <Button size="sm" variant="outline" disabled={removeOverride.isPending}
                          onClick={() => removeOverride.mutate()}>
                    Remove override
                  </Button>
                </div>
              )}

              <div className="flex flex-wrap gap-2">
                {canRefresh(data) && (
                  <Button size="sm" variant="outline" disabled={refresh.isPending}
                          onClick={() => refresh.mutate()}>
                    <RefreshCw size={14} aria-hidden="true" />
                    Re-verify address
                  </Button>
                )}
                {canOverride(data) && !asking && (
                  <Button size="sm" variant="outline" onClick={() => setAsking(true)}>
                    <MailCheck size={14} aria-hidden="true" />
                    Allow sending anyway
                  </Button>
                )}
              </div>

              {asking && (
                <div className="space-y-2">
                  <Label htmlFor={`override-${leadId}`}>
                    Why is this address safe to email? (recorded in the audit log)
                  </Label>
                  <Input id={`override-${leadId}`} value={reason}
                         onChange={(e) => setReason(e.target.value)}
                         placeholder="e.g. they emailed us from this address last week" />
                  <div className="flex gap-2">
                    <Button size="sm" disabled={override.isPending || reason.trim().length < 5}
                            onClick={() => override.mutate()}>
                      Confirm — allow sending
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setAsking(false)}>
                      Cancel
                    </Button>
                  </div>
                </div>
              )}

              {data.attempts.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Lookups ({totalCostUnits(data.attempts)} paid unit
                    {totalCostUnits(data.attempts) === 1 ? "" : "s"})
                  </p>
                  <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                    {data.attempts.slice(0, 8).map((a) => (
                      <li key={a.id}>{attemptText(a)}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}
