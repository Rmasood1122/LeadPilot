"use client";

/** CRM dashboard — page 2: lead analytics.
 *
 * Velocity (time in stage), where leads came from, what Hunter made of their
 * addresses, and which leads have gone quiet.
 *
 * A note on honesty, because it shapes this page: time-in-stage needs the
 * moment the current status was entered, and nothing recorded that before
 * M9. Migration 0019 deliberately does not invent one. So each velocity row
 * reports how many of its leads are really measured and how many are
 * estimated from updated_at, and the UI SAYS SO instead of presenting one
 * confident average built partly on a guess.
 */

import { useState } from "react";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useCrmLeadsAnalytics } from "@/lib/api/crm-hooks";
import { StrategyScope } from "@/components/crm/CrmChrome";
import {
  SectionHeading,
  StatTile,
  formatCount,
  formatRate,
  stageLabel,
  useChartPalette,
} from "@/components/crm/dashboard/primitives";
import { AsyncState } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const STUCK_THRESHOLDS = [3, 7, 14, 30];

export default function CrmLeadAnalyticsPage() {
  const [strategyId, setStrategyId] = useState("");
  const [stuckAfter, setStuckAfter] = useState(7);
  const { data, isLoading, error } = useCrmLeadsAnalytics(
    strategyId || null,
    stuckAfter,
  );
  const palette = useChartPalette();

  const velocity = (data?.velocity ?? []).filter((row) => row.leads > 0);
  const sources = data?.sources ?? [];
  const verification = data?.verification;

  const sourceColors = [
    palette.primary,
    palette.accent,
    palette.success,
    palette.warning,
    palette.muted,
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionHeading
          title="Lead analytics"
          hint="How fast leads move, where they come from, and which have gone quiet."
        />
        <StrategyScope value={strategyId} onChange={setStrategyId} />
      </div>

      <AsyncState
        isLoading={isLoading}
        error={error}
        empty={!!data && velocity.length === 0 && sources.length === 0}
        emptyLabel="No leads yet — nothing to analyse."
      >
        {data && verification && (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile
                label="Deliverable"
                value={formatRate(verification.verified_ratio)}
                sub={`${formatCount(verification.verified)} of ${formatCount(verification.total)} verified`}
                tone={
                  verification.verified_ratio !== null &&
                  verification.verified_ratio < 0.6
                    ? "warning"
                    : "positive"
                }
                title="Share of the addresses Hunter actually checked that came back deliverable. Leads that never reached verification are excluded."
              />
              <StatTile
                label="Risky"
                value={formatCount(verification.flagged)}
                tone={verification.flagged > 0 ? "warning" : "default"}
                sub="Flagged by the verifier"
              />
              <StatTile
                label="Undeliverable"
                value={formatCount(verification.dropped)}
                tone={verification.dropped > 0 ? "danger" : "default"}
                sub="Dropped or suppressed"
              />
              <StatTile
                label={`Idle > ${stuckAfter}d`}
                value={formatCount(data.stuck_count)}
                tone={data.stuck_count > 0 ? "warning" : "positive"}
                sub="Excludes booked and dropped"
              />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Average time in stage</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Stages marked{" "}
                    <span className="font-medium">estimated</span> contain leads
                    that last moved before stage history was recorded; their
                    figure is derived from the last update, not a real stage
                    entry.
                  </p>
                </CardHeader>
                <CardContent>
                  {velocity.length > 0 ? (
                    <ResponsiveContainer width="100%" height={Math.max(160, velocity.length * 34)}>
                      <BarChart
                        data={velocity.map((row) => ({
                          ...row,
                          label: stageLabel(row.stage),
                        }))}
                        layout="vertical"
                        margin={{ left: 8, right: 16 }}
                      >
                        <XAxis
                          type="number"
                          tick={{ fontSize: 10, fill: palette.muted }}
                          tickLine={false}
                          axisLine={false}
                          unit="d"
                        />
                        <YAxis
                          type="category"
                          dataKey="label"
                          width={110}
                          tick={{ fontSize: 11, fill: palette.muted }}
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
                          formatter={(value: number) => [`${value} days`, "Average"]}
                        />
                        <Bar dataKey="avg_days_in_stage" name="Avg days">
                          {velocity.map((row) => (
                            <Cell
                              key={row.stage}
                              // Estimated stages are drawn in the muted tone
                              // so the eye does not treat them as equally
                              // trustworthy as the measured ones.
                              fill={row.fully_measured ? palette.primary : palette.muted}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-sm text-muted-foreground">No leads in flight.</p>
                  )}

                  <ul className="mt-3 space-y-1 text-xs">
                    {velocity.map((row) => (
                      <li key={row.stage} className="flex items-center gap-2">
                        <span className="w-28 truncate text-muted-foreground">
                          {stageLabel(row.stage)}
                        </span>
                        <span className="tabular-nums">
                          {row.avg_days_in_stage}d over {formatCount(row.leads)}
                        </span>
                        {!row.fully_measured && (
                          <Badge tone="warning" title={`${row.estimated} of ${row.leads} estimated from last update`}>
                            estimated
                          </Badge>
                        )}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Lead sources</CardTitle>
                </CardHeader>
                <CardContent>
                  {sources.length > 0 ? (
                    <div className="flex items-center gap-4">
                      <ResponsiveContainer width="55%" height={180}>
                        <PieChart>
                          <Pie
                            data={sources}
                            dataKey="count"
                            nameKey="source"
                            innerRadius={40}
                            outerRadius={70}
                            paddingAngle={2}
                          >
                            {sources.map((source, index) => (
                              <Cell
                                key={source.source}
                                fill={sourceColors[index % sourceColors.length]}
                              />
                            ))}
                          </Pie>
                          <Tooltip
                            contentStyle={{
                              fontSize: 12,
                              background: "rgb(var(--card))",
                              border: `1px solid ${palette.border}`,
                              borderRadius: "var(--radius)",
                              color: "rgb(var(--card-foreground))",
                            }}
                          />
                        </PieChart>
                      </ResponsiveContainer>
                      <ul className="flex-1 space-y-1.5 text-sm">
                        {sources.map((source, index) => (
                          <li key={source.source} className="flex items-center gap-2">
                            <span
                              className="h-2.5 w-2.5 shrink-0 rounded-sm"
                              style={{
                                backgroundColor:
                                  sourceColors[index % sourceColors.length],
                              }}
                              aria-hidden="true"
                            />
                            <span className="flex-1 truncate capitalize">
                              {source.source}
                            </span>
                            <span className="tabular-nums text-muted-foreground">
                              {formatCount(source.count)}
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground">No leads sourced yet.</p>
                  )}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader className="flex-row items-center justify-between">
                <div>
                  <CardTitle className="text-sm">Stuck leads</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Sitting in the same stage without moving. Booked and dropped
                    leads are excluded — they are finished, not stuck.
                  </p>
                </div>
                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  Idle for
                  <select
                    className="rounded border border-border bg-card px-2 py-1 text-sm text-foreground"
                    value={stuckAfter}
                    onChange={(event) => setStuckAfter(Number(event.target.value))}
                    aria-label="Stuck-lead threshold in days"
                  >
                    {STUCK_THRESHOLDS.map((days) => (
                      <option key={days} value={days}>
                        {days} days
                      </option>
                    ))}
                  </select>
                </label>
              </CardHeader>
              <CardContent>
                {data.stuck_leads.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Nothing has been idle for {stuckAfter} days.
                  </p>
                ) : (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="border-b border-border text-left text-xs text-muted-foreground">
                            <th className="pb-2 font-medium">Stage</th>
                            <th className="pb-2 text-right font-medium">Days idle</th>
                            <th className="pb-2 font-medium">Measurement</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.stuck_leads.map((lead) => (
                            <tr key={lead.lead_id} className="border-b border-border/40">
                              <td className="py-1.5">{stageLabel(lead.status)}</td>
                              <td className="py-1.5 text-right tabular-nums">
                                {lead.days_in_stage}
                              </td>
                              <td className="py-1.5">
                                <Badge tone={lead.measured ? "default" : "warning"}>
                                  {lead.measured ? "measured" : "estimated"}
                                </Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {data.stuck_count > data.stuck_leads.length && (
                      <p className="mt-2 text-xs text-muted-foreground">
                        Showing the {data.stuck_leads.length} longest-idle of{" "}
                        {formatCount(data.stuck_count)}.
                      </p>
                    )}
                  </>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </AsyncState>
    </div>
  );
}
