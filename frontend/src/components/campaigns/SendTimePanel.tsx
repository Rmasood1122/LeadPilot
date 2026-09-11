"use client";

/** Feature Group 3: the campaign's smart-send-time toggle, its top windows,
 *  and the day x hour engagement heatmap they come from (lead local time). */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import {
  getSendTime,
  recomputeSendTime,
  setSmartSendTime,
  type HeatCell,
} from "@/lib/api/revenue";
import { AsyncState } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { DOW_LABELS, formatWindow, heatAlpha } from "@/lib/revenue";
import { cn } from "@/lib/utils";

const HOURS = Array.from({ length: 24 }, (_, h) => h);

export function SendTimePanel({ strategyId }: { strategyId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const key = ["send-time", strategyId];
  const { data, isLoading, error } = useQuery({
    queryKey: key,
    queryFn: () => getSendTime(strategyId),
    enabled: !!strategyId,
  });

  const toggle = useMutation({
    mutationFn: (on: boolean) => setSmartSendTime(strategyId, on),
    onSuccess: (res) => {
      qc.setQueryData(key, res);
      const moved = res.rescheduled ? ` — ${res.rescheduled} scheduled steps moved` : "";
      toast(res.smart_send_time ? `Smart send time on${moved}` : "Smart send time off", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const recompute = useMutation({
    mutationFn: () => recomputeSendTime(strategyId),
    onSuccess: (res) => {
      qc.setQueryData(key, res);
      toast(res.result === "insufficient_data" ? "Not enough opens yet" : "Windows recomputed", "info");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const cells = new Map<string, HeatCell>(
    (data?.heatmap ?? []).map((c) => [`${c.dow}-${c.hour}`, c]),
  );
  const maxScore = Math.max(0, ...(data?.heatmap ?? []).map((c) => c.score));
  const windowKeys = new Set((data?.windows ?? []).map((w) => `${w.dow}-${w.hour}`));
  const ready = !!data && data.opens >= data.min_opens;
  const on = !!data?.smart_send_time;

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-sm">Smart send time</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Holds future steps for this campaign&apos;s top engagement windows,
            in each lead&apos;s local time.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-label="Smart send time"
          disabled={!data || toggle.isPending}
          onClick={() => toggle.mutate(!on)}
          className={cn(
            "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-border transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--primary))] disabled:opacity-50",
            on ? "bg-[rgb(var(--primary))]" : "bg-muted",
          )}
        >
          <span
            className={cn(
              "inline-block h-4 w-4 rounded-full bg-card shadow transition-transform",
              on ? "translate-x-6" : "translate-x-1",
            )}
          />
        </button>
      </CardHeader>
      <CardContent className="space-y-4">
        <AsyncState isLoading={isLoading} error={error}>
          {data && (
            <>
              {!ready ? (
                <p className="text-sm text-muted-foreground">
                  Collecting data: <span className="font-medium text-foreground">{data.opens}</span>{" "}
                  of {data.min_opens} opens. Windows are computed once the campaign
                  reaches {data.min_opens} opens; until then every step sends on the
                  normal schedule{on ? " and smart send time takes over automatically" : ""}.
                </p>
              ) : data.windows.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No engagement has landed inside your send window yet, so there
                  are no windows to schedule into.
                </p>
              ) : (
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Top windows
                  </p>
                  <ol className="space-y-1 text-sm">
                    {data.windows.map((w, i) => (
                      <li key={`${w.dow}-${w.hour}`} className="flex flex-wrap items-baseline gap-x-2">
                        <span className="w-4 text-muted-foreground">{i + 1}.</span>
                        <span className="font-medium">{formatWindow(w.dow, w.hour)}</span>
                        <span className="text-xs text-muted-foreground">
                          {(w.share * 100).toFixed(0)}% of engagement · {w.opens} opens · {w.replies} replies
                        </span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}

              {data.heatmap.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="border-separate text-[10px]" style={{ borderSpacing: 2 }}
                         aria-label="Engagement by day and hour (lead local time)">
                    <thead>
                      <tr>
                        <th />
                        {HOURS.map((h) => (
                          <th key={h} className="w-5 text-center font-normal text-muted-foreground">
                            {h % 3 === 0 ? h : ""}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {DOW_LABELS.map((label, dow) => (
                        <tr key={label}>
                          <th scope="row" className="pr-1 text-left font-normal text-muted-foreground">
                            {label}
                          </th>
                          {HOURS.map((hour) => {
                            const c = cells.get(`${dow}-${hour}`);
                            const alpha = c ? heatAlpha(c.score, maxScore) : 0;
                            const top = windowKeys.has(`${dow}-${hour}`);
                            return (
                              <td
                                key={hour}
                                className={cn(
                                  "h-5 w-5 rounded-sm border border-border/60",
                                  top && "ring-2 ring-[rgb(var(--foreground))]",
                                  c && !c.schedulable && "opacity-50",
                                )}
                                style={alpha ? { backgroundColor: `rgb(var(--primary) / ${alpha.toFixed(2)})` } : undefined}
                                title={c
                                  ? `${formatWindow(dow, hour)}: ${c.opens} opens, ${c.replies} replies` +
                                    (c.schedulable ? "" : " (outside your send window)")
                                  : `${formatWindow(dow, hour)}: no engagement`}
                              />
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Darker = more engagement (a reply counts 3× an open) · outlined = a
                    top window · faded = outside your send window, never scheduled.
                  </p>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
                <span>
                  {data.computed_at
                    ? `Windows last computed ${new Date(data.computed_at).toLocaleString()}. `
                    : ""}
                  A step is never held more than {data.max_delay_hours} h.
                </span>
                <Button
                  variant="outline"
                  onClick={() => recompute.mutate()}
                  disabled={recompute.isPending || !ready}
                >
                  <RefreshCw className="mr-1 h-3.5 w-3.5" aria-hidden /> Recompute
                </Button>
              </div>
            </>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}
