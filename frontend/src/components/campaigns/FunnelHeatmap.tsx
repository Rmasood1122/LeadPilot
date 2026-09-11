"use client";

/** Feature Group 3: per-step conversion funnel as a heatmap table.
 *
 *  A table, not a chart: the reader's question is "which step?", and a row
 *  per step with the numbers in it answers that directly. Colour is a single
 *  sequential hue (the theme's primary) scaled PER COLUMN, so the strongest
 *  step in each measure stands out without one busy column washing out the
 *  rest. Every cell carries its exact count in a tooltip. */

import { useQuery } from "@tanstack/react-query";
import { getFunnel, type FunnelStep } from "@/lib/api/revenue";
import { AsyncState } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatRate } from "@/components/crm/dashboard/primitives";
import { heatAlpha, heatTextClass } from "@/lib/revenue";
import { cn } from "@/lib/utils";

type RateKey = "open_rate" | "reply_rate" | "booking_rate" | "drop_off_rate";

const COLUMNS: { key: RateKey; label: string; count: keyof FunnelStep; noun: string }[] = [
  { key: "open_rate", label: "Opened", count: "opened", noun: "opened" },
  { key: "reply_rate", label: "Replied", count: "replied", noun: "replied" },
  { key: "booking_rate", label: "Booked", count: "booked", noun: "booked a meeting" },
  { key: "drop_off_rate", label: "Dropped off", count: "dropped", noun: "stopped here" },
];

export function FunnelHeatmap({ strategyId }: { strategyId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["funnel", strategyId],
    queryFn: () => getFunnel(strategyId),
    enabled: !!strategyId,
  });

  const steps = data?.sequences.flatMap((s) => s.steps) ?? [];
  const max: Record<RateKey, number> = {
    open_rate: 0, reply_rate: 0, booking_rate: 0, drop_off_rate: 0,
  };
  for (const c of COLUMNS) {
    max[c.key] = Math.max(0, ...steps.map((s) => s[c.key] ?? 0));
  }

  return (
    <AsyncState
      isLoading={isLoading}
      error={error}
      empty={!data || data.sequences.length === 0}
      emptyLabel="No sequences in this campaign yet."
    >
      {data && (
        <div className="space-y-4">
          {data.best_step ? (
            <p className="text-sm">
              <span className="font-medium">Best converting step:</span>{" "}
              {data.best_step.sequence_name} · step {data.best_step.step_no} —{" "}
              {formatRate(data.best_step.reply_rate)} reply rate
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              A best step is named once one has been sent to at least{" "}
              {data.best_step_min_sent ?? 20} leads.
            </p>
          )}

          {data.sequences.map((seq) => (
            <Card key={seq.id}>
              <CardHeader>
                <CardTitle className="text-sm">{seq.name}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table
                    className="w-full min-w-[640px] border-separate text-sm"
                    style={{ borderSpacing: 2 }}
                    aria-label={`Step funnel for ${seq.name}`}
                  >
                    <thead>
                      <tr className="text-left text-xs text-muted-foreground">
                        <th className="pb-1 font-medium">Step</th>
                        <th className="pb-1 font-medium">Channel</th>
                        <th className="pb-1 text-right font-medium">Sent</th>
                        {COLUMNS.map((c) => (
                          <th key={c.key} className="pb-1 text-center font-medium">{c.label}</th>
                        ))}
                        <th className="pb-1 text-right font-medium" title="Still enrolled, waiting for the next step">
                          Waiting
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {seq.steps.map((step) => (
                        <tr key={step.step_no}>
                          <td className="py-1 pr-2 font-medium">
                            Step {step.step_no}
                            {step.variant !== "A" ? ` (${step.variant})` : ""}
                          </td>
                          <td className="pr-2 capitalize text-muted-foreground">{step.channel}</td>
                          <td className="pr-2 text-right tabular-nums">{step.sent}</td>
                          {COLUMNS.map((c) => {
                            const rate = step[c.key];
                            const alpha = rate === null ? 0 : heatAlpha(rate, max[c.key]);
                            return (
                              <td
                                key={c.key}
                                className={cn(
                                  "rounded px-2 py-1.5 text-center tabular-nums",
                                  rate === null ? "text-muted-foreground" : heatTextClass(alpha),
                                )}
                                style={alpha ? { backgroundColor: `rgb(var(--primary) / ${alpha.toFixed(2)})` } : undefined}
                                title={rate === null
                                  ? "Not tracked on this channel"
                                  : `${step[c.count]} of ${step.sent} leads ${c.noun}`}
                              >
                                {formatRate(rate)}
                              </td>
                            );
                          })}
                          <td className="text-right tabular-nums text-muted-foreground">
                            {step.in_progress}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          ))}

          <p className="text-xs text-muted-foreground">
            Shading is relative within each column — the darkest cell is that
            measure&apos;s strongest step. Replies and bookings without a
            message link count toward the last step the lead received before
            responding. Open rates rely on the tracking pixel (not added for
            EU/UK leads) and are inflated by Apple Mail Privacy Protection;
            treat them as directional.
          </p>
        </div>
      )}
    </AsyncState>
  );
}
