"use client";

/** CRM dashboard — page 3: campaign and outreach performance.
 *
 * Per-sequence and per-channel reply/booking rates, A/B variant comparison,
 * and bounce rate against the 3% auto-pause threshold that the sequence
 * engine actually enforces.
 *
 * Rates are computed server-side against sent + bounced, matching what the
 * existing campaign endpoint calls "sent". A bounced message WAS dispatched;
 * dropping it from the denominator would flatter the reply rate at exactly
 * the moment deliverability is worst.
 */

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { useCrmCampaigns } from "@/lib/api/crm-hooks";
import { StrategyScope } from "@/components/crm/CrmChrome";
import {
  SectionHeading,
  StatTile,
  formatCount,
  formatRate,
  useChartPalette,
} from "@/components/crm/dashboard/primitives";
import { AsyncState } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function CrmCampaignsPage() {
  const [strategyId, setStrategyId] = useState("");
  const { data, isLoading, error } = useCrmCampaigns(strategyId || null);
  const palette = useChartPalette();

  const channels = data?.channels ?? [];
  const variants = data?.variants ?? [];
  const sequences = data?.sequences ?? [];
  const bounce = data?.bounce;

  const totalSent = channels.reduce((sum, channel) => sum + channel.sent, 0);
  const totalReplied = channels.reduce((sum, channel) => sum + channel.replied, 0);
  const totalBooked = channels.reduce((sum, channel) => sum + channel.booked, 0);

  const tooltipStyle = {
    fontSize: 12,
    background: "rgb(var(--card))",
    border: `1px solid ${palette.border}`,
    borderRadius: "var(--radius)",
    color: "rgb(var(--card-foreground))",
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionHeading
          title="Campaign performance"
          hint="Sequences, channels and A/B variants — measured against messages actually dispatched."
        />
        <StrategyScope value={strategyId} onChange={setStrategyId} />
      </div>

      <AsyncState
        isLoading={isLoading}
        error={error}
        empty={!!data && totalSent === 0 && sequences.length === 0}
        emptyLabel="Nothing sent yet. Start a sequence to see performance here."
      >
        {data && bounce && (
          <>
            {data.paused_campaigns.length > 0 && (
              <div
                role="alert"
                className="rounded border border-[rgb(var(--warning))]/40 bg-card p-3 text-sm"
              >
                <p className="font-medium text-[rgb(var(--warning))]">
                  {data.paused_campaigns.length} campaign
                  {data.paused_campaigns.length === 1 ? " is" : "s are"} paused
                </p>
                <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
                  {data.paused_campaigns.map((campaign) => (
                    <li key={campaign.strategy_id}>
                      <span className="font-medium text-foreground">
                        {campaign.product_name}
                      </span>{" "}
                      — {campaign.reason ?? campaign.campaign_state}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <StatTile
                label="Dispatched"
                value={formatCount(totalSent)}
                sub="Sent + bounced"
                title="A bounced message was still dispatched, so it counts in the denominator of every rate on this page."
              />
              <StatTile
                label="Reply rate"
                value={formatRate(totalSent ? totalReplied / totalSent : null)}
                sub={`${formatCount(totalReplied)} replies`}
              />
              <StatTile
                label="Booking rate"
                value={formatRate(totalSent ? totalBooked / totalSent : null)}
                sub={`${formatCount(totalBooked)} meetings`}
                tone={totalBooked > 0 ? "positive" : "default"}
              />
              <StatTile
                label="Bounce rate"
                value={formatRate(bounce.sent ? bounce.rate : null)}
                sub={`Auto-pause at ${formatRate(bounce.pause_threshold, 0)}`}
                tone={bounce.over_threshold ? "danger" : "positive"}
                title="The sequence engine pauses a campaign automatically once this crosses the threshold."
              />
            </div>

            {bounce.over_threshold && (
              <div
                role="alert"
                className="rounded border border-[rgb(var(--destructive))]/40 bg-card p-3 text-sm"
              >
                <span className="font-medium text-[rgb(var(--destructive))]">
                  Bounce rate is over the auto-pause threshold.
                </span>{" "}
                <span className="text-muted-foreground">
                  {formatCount(bounce.bounced)} of {formatCount(bounce.sent)}{" "}
                  dispatched messages bounced ({formatRate(bounce.rate)} against a{" "}
                  {formatRate(bounce.pause_threshold, 0)} limit). Sending pauses
                  itself to protect the domain.
                </span>
              </div>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Channel comparison</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart
                      data={channels.map((channel) => ({
                        channel: channel.channel,
                        Replies: channel.replied,
                        Bookings: channel.booked,
                        Bounces: channel.bounced,
                      }))}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke={palette.border}
                        vertical={false}
                      />
                      <XAxis
                        dataKey="channel"
                        tick={{ fontSize: 11, fill: palette.muted }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <YAxis
                        allowDecimals={false}
                        width={30}
                        tick={{ fontSize: 10, fill: palette.muted }}
                        tickLine={false}
                        axisLine={false}
                      />
                      <Tooltip cursor={{ fill: palette.border, opacity: 0.3 }} contentStyle={tooltipStyle} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="Replies" fill={palette.primary} />
                      <Bar dataKey="Bookings" fill={palette.success} />
                      <Bar dataKey="Bounces" fill={palette.destructive} />
                    </BarChart>
                  </ResponsiveContainer>

                  <table className="mt-3 w-full text-sm">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="pb-2 font-medium">Channel</th>
                        <th className="pb-2 text-right font-medium">Sent</th>
                        <th className="pb-2 text-right font-medium">Reply</th>
                        <th className="pb-2 text-right font-medium">Booked</th>
                      </tr>
                    </thead>
                    <tbody>
                      {channels.map((channel) => (
                        <tr key={channel.channel} className="border-b border-border/40">
                          <td className="py-1.5 capitalize">{channel.channel}</td>
                          <td className="py-1.5 text-right tabular-nums">
                            {formatCount(channel.sent)}
                          </td>
                          <td className="py-1.5 text-right tabular-nums">
                            {formatRate(channel.reply_rate)}
                          </td>
                          <td className="py-1.5 text-right tabular-nums">
                            {formatRate(channel.booking_rate)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">A/B variants</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    The same aggregation the auto-promotion engine reads, so
                    this and the promotion decision cannot disagree.
                  </p>
                </CardHeader>
                <CardContent>
                  {variants.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No variant data yet.
                    </p>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-xs text-muted-foreground">
                          <th className="pb-2 font-medium">Variant</th>
                          <th className="pb-2 text-right font-medium">Sent</th>
                          <th className="pb-2 text-right font-medium">Reply</th>
                          <th className="pb-2 text-right font-medium">Booked</th>
                        </tr>
                      </thead>
                      <tbody>
                        {variants.map((variant) => (
                          <tr key={variant.variant} className="border-b border-border/40">
                            <td className="py-1.5 font-medium">{variant.variant}</td>
                            <td className="py-1.5 text-right tabular-nums">
                              {formatCount(variant.sent)}
                            </td>
                            <td className="py-1.5 text-right tabular-nums">
                              {formatRate(variant.reply_rate)}
                            </td>
                            <td className="py-1.5 text-right tabular-nums">
                              {formatRate(variant.booking_rate)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                  {variants.some((variant) => variant.sent < 30) && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      A variant with under 30 sends is below the sample size the
                      promotion engine requires — read these as early signal,
                      not a result.
                    </p>
                  )}
                </CardContent>
              </Card>
            </div>

            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Sequences</CardTitle>
              </CardHeader>
              <CardContent>
                {sequences.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No sequences have sent anything yet.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-xs text-muted-foreground">
                          <th className="pb-2 font-medium">Sequence</th>
                          <th className="pb-2 font-medium">Channel</th>
                          <th className="pb-2 font-medium">State</th>
                          <th className="pb-2 text-right font-medium">Sent</th>
                          <th className="pb-2 text-right font-medium">Reply</th>
                          <th className="pb-2 text-right font-medium">Booked</th>
                        </tr>
                      </thead>
                      <tbody>
                        {sequences.map((sequence) => (
                          <tr key={sequence.sequence_id} className="border-b border-border/40">
                            <td className="py-1.5 font-medium">{sequence.name}</td>
                            <td className="py-1.5 capitalize">{sequence.channel}</td>
                            <td className="py-1.5">
                              <Badge tone={sequence.status === "active" ? "success" : "default"}>
                                {sequence.status}
                              </Badge>
                            </td>
                            <td className="py-1.5 text-right tabular-nums">
                              {formatCount(sequence.sent)}
                            </td>
                            <td className="py-1.5 text-right tabular-nums">
                              {formatRate(sequence.reply_rate)}
                            </td>
                            <td className="py-1.5 text-right tabular-nums">
                              {formatRate(sequence.booking_rate)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>
          </>
        )}
      </AsyncState>
    </div>
  );
}
