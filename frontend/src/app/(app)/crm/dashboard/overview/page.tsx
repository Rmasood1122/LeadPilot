"use client";

/** CRM dashboard — page 1: pipeline overview.
 *
 * Funnel by stage, stage-to-stage conversion, active leads, meetings booked
 * this week and month, a 30-day booking trend, and the strategy producing
 * the most meetings. Every figure comes from GET /crm/dashboard/pipeline,
 * which aggregates in SQL — there is no derived-in-the-browser number on
 * this page and no placeholder.
 */

import { useState } from "react";
import { BarChart, Bar, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { useCrmPipeline } from "@/lib/api/crm-hooks";
import { StrategyScope } from "@/components/crm/CrmChrome";
import { FunnelChart } from "@/components/crm/dashboard/FunnelChart";
import {
  SectionHeading,
  Sparkline,
  StatTile,
  formatCount,
  formatRate,
  useChartPalette,
} from "@/components/crm/dashboard/primitives";
import { AsyncState } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function CrmOverviewPage() {
  const [strategyId, setStrategyId] = useState("");
  const { data, isLoading, error } = useCrmPipeline(strategyId || null);
  const palette = useChartPalette();

  const trend = data?.bookings_trend ?? [];
  // Overall conversion, sourced -> booked. Read off the funnel rather than
  // recomputed: the two must agree, and one source of truth is how that is
  // guaranteed.
  const firstStage = data?.funnel[0];
  const lastStage = data?.funnel[data.funnel.length - 1];
  const endToEnd =
    firstStage && lastStage && firstStage.reached > 0
      ? lastStage.reached / firstStage.reached
      : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionHeading
          title="Pipeline overview"
          hint="Every lead in the account, by stage."
        />
        <StrategyScope value={strategyId} onChange={setStrategyId} />
      </div>

      <AsyncState
        isLoading={isLoading}
        error={error}
        empty={!!data && data.total_leads === 0}
        emptyLabel="No leads yet. Source leads from a campaign to fill the pipeline."
      >
        {data && (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile
                label="Active leads"
                value={formatCount(data.active_leads)}
                sub={`${formatCount(data.total_leads)} total`}
                title="Excludes dropped leads and booked meetings — those are finished, not in flight."
              />
              <StatTile
                label="Booked this week"
                value={formatCount(data.meetings_booked_week)}
                tone={data.meetings_booked_week > 0 ? "positive" : "default"}
                sub="Last 7 days"
              />
              <StatTile
                label="Booked this month"
                value={formatCount(data.meetings_booked_month)}
                sub="Last 30 days"
              />
              <StatTile
                label="Sourced to booked"
                value={formatRate(endToEnd)}
                sub="End-to-end conversion"
                title="Leads that reached a booked meeting, as a share of every lead sourced."
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <FunnelChart stages={data.funnel} />
              </div>

              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Bookings, last 30 days</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <Sparkline
                      points={trend.map((point) => point.count)}
                      label="Meetings booked per day over the last 30 days"
                      height={44}
                    />
                    {trend.length > 0 ? (
                      <ResponsiveContainer width="100%" height={120}>
                        <BarChart data={trend}>
                          <XAxis
                            dataKey="bucket"
                            tick={{ fontSize: 10, fill: palette.muted }}
                            tickLine={false}
                            axisLine={false}
                            // Only the endpoints: thirty date labels in a
                            // 300px card is an unreadable smear.
                            interval="preserveStartEnd"
                          />
                          <YAxis
                            allowDecimals={false}
                            width={24}
                            tick={{ fontSize: 10, fill: palette.muted }}
                            tickLine={false}
                            axisLine={false}
                          />
                          <Tooltip
                            cursor={{ fill: palette.border, opacity: 0.3 }}
                            contentStyle={{
                              fontSize: 12,
                              background: "rgb(var(--card))",
                              border: `1px solid ${palette.border}`,
                              borderRadius: "var(--radius)",
                              color: "rgb(var(--card-foreground))",
                            }}
                          />
                          <Bar dataKey="count" name="Booked" fill={palette.primary} />
                        </BarChart>
                      </ResponsiveContainer>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        No meetings booked in the last 30 days.
                      </p>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Top strategy</CardTitle>
                  </CardHeader>
                  <CardContent>
                    {data.top_strategy ? (
                      <>
                        <p className="truncate font-medium">
                          {data.top_strategy.product_name}
                        </p>
                        <p className="text-sm text-muted-foreground">
                          {formatCount(data.top_strategy.meetings_booked)} meeting
                          {data.top_strategy.meetings_booked === 1 ? "" : "s"} booked
                        </p>
                      </>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No meetings booked yet — nothing to rank.
                      </p>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>
          </>
        )}
      </AsyncState>
    </div>
  );
}
