"use client";

/** Feature Group 3: weekly reply sentiment for one campaign.
 *
 *  Two rates on ONE percentage axis (objection rate, the thing the alert
 *  watches, and interested rate for context). The objection line is the
 *  theme primary and solid; the interested line is muted and dashed, so the
 *  two differ by more than hue. Weeks with no replies are gaps, not zeros. */

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import {
  CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { getSentiment } from "@/lib/api/revenue";
import { AsyncState } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatRate, useChartPalette } from "@/components/crm/dashboard/primitives";
import { objectionChange, sentimentChartData } from "@/lib/revenue";

export function SentimentTrend({ strategyId }: { strategyId: string }) {
  const palette = useChartPalette();
  const { data, isLoading, error } = useQuery({
    queryKey: ["sentiment", strategyId],
    queryFn: () => getSentiment(strategyId, 12),
    enabled: !!strategyId,
  });

  const rows = data ? sentimentChartData(data.weeks) : [];
  const change = data ? objectionChange(data.weeks) : null;
  const alerted = data ? [...data.weeks].reverse().find((w) => w.alerted) : undefined;
  const replies = (data?.weeks ?? []).reduce((n, w) => n + w.total, 0);

  return (
    <AsyncState
      isLoading={isLoading}
      error={error}
      empty={!data || replies === 0}
      emptyLabel="No human replies in the last 12 weeks."
    >
      {data && (
        <div className="space-y-4">
          {alerted && (
            <div role="alert" className="flex gap-3 rounded border border-warning bg-card p-3 text-sm">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[rgb(var(--warning))]" aria-hidden />
              <div>
                <p className="font-medium">Objection spike — week of {alerted.week_start}</p>
                <p className="text-muted-foreground">
                  Objections were {formatRate(alerted.objection_rate, 0)} of human replies
                  ({alerted.objection} of {alerted.total}). Alerts fire when the rate rises more
                  than {Math.round(data.threshold * 100)}% week over week, with at least{" "}
                  {data.min_replies} replies in both weeks.
                </p>
              </div>
            </div>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Reply sentiment by week</CardTitle>
              <p className="text-xs text-muted-foreground">
                Share of human replies. Out-of-office, bounces and automated responses are excluded.
                {change !== null &&
                  ` Objections ${change >= 0 ? "up" : "down"} ${Math.abs(change)} pts vs the previous week.`}
              </p>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
                  <CartesianGrid stroke={palette.border} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="week" tick={{ fontSize: 11, fill: palette.muted }} stroke={palette.border} />
                  <YAxis unit="%" domain={[0, 100]} width={44}
                         tick={{ fontSize: 11, fill: palette.muted }} stroke={palette.border} />
                  <Tooltip
                    formatter={(value) => (value === null || value === undefined ? "—" : `${value}%`)}
                    labelFormatter={(label, payload) => {
                      const row = payload?.[0]?.payload as { total?: number; partial?: boolean } | undefined;
                      if (!row) return String(label);
                      return `Week of ${label} · ${row.total ?? 0} replies${row.partial ? " (so far)" : ""}`;
                    }}
                    contentStyle={{
                      background: "rgb(var(--card))",
                      border: `1px solid ${palette.border}`,
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="objection" name="Objection rate"
                        stroke={palette.primary} strokeWidth={2} dot={{ r: 4 }} connectNulls={false} />
                  <Line type="monotone" dataKey="interested" name="Interested rate"
                        stroke={palette.muted} strokeWidth={2} strokeDasharray="5 4"
                        dot={{ r: 4 }} connectNulls={false} />
                </LineChart>
              </ResponsiveContainer>

              <details className="mt-3">
                <summary className="cursor-pointer text-xs text-muted-foreground">Show weekly table</summary>
                <div className="mt-2 overflow-x-auto">
                  <table className="w-full min-w-[560px] text-sm" aria-label="Weekly reply classifications">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-1 font-medium">Week of</th>
                        <th className="text-right font-medium">Replies</th>
                        <th className="text-right font-medium">Interested</th>
                        <th className="text-right font-medium">Questions</th>
                        <th className="text-right font-medium">Objections</th>
                        <th className="text-right font-medium">Not interested</th>
                        <th className="text-right font-medium">Unsubscribed</th>
                        <th className="text-right font-medium">Objection rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.weeks.map((w) => (
                        <tr key={w.week_start} className="border-b border-border/50 tabular-nums">
                          <td className="py-1">
                            {w.week_start}
                            {w.partial ? " (so far)" : ""}
                            {w.alerted ? " ⚠" : ""}
                          </td>
                          <td className="text-right">{w.total}</td>
                          <td className="text-right">{w.interested}</td>
                          <td className="text-right">{w.question}</td>
                          <td className="text-right">{w.objection}</td>
                          <td className="text-right">{w.not_interested}</td>
                          <td className="text-right">{w.unsubscribe}</td>
                          <td className="text-right">{formatRate(w.objection_rate)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            </CardContent>
          </Card>
        </div>
      )}
    </AsyncState>
  );
}
