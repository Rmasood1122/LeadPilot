"use client";

import type { ChannelStats } from "@/lib/api/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { pct } from "@/lib/utils";

export function ChannelCard({
  name,
  stats,
}: {
  name: "Gmail" | "WhatsApp";
  stats: ChannelStats;
}) {
  const cap = stats.daily_cap_today;
  const sends = stats.sends_today ?? 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Sends today</span>
          <span>
            {sends}
            {cap != null && ` / ${cap}`}
            {cap != null && cap < 100 && (
              <span className="ml-1 text-xs text-muted-foreground">(warm-up)</span>
            )}
          </span>
        </div>
        {cap != null && (
          <div className="h-2 overflow-hidden rounded bg-muted" role="progressbar"
               aria-label={`${name} daily sends`} aria-valuenow={sends}
               aria-valuemax={cap}>
            <div className="h-full bg-primary"
                 style={{ width: `${Math.min(100, (sends / Math.max(cap, 1)) * 100)}%` }} />
          </div>
        )}
        <div className="flex justify-between">
          <span className="text-muted-foreground">Delivery rate</span>
          <span>{pct(stats.delivery_rate)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Reply rate</span>
          <span>{pct(stats.reply_rate)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Total sent</span>
          <span>{stats.sent_total}</span>
        </div>
        {name === "WhatsApp" && (
          <>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Open 24h windows</span>
              <span>{stats.window_open_count ?? 0}</span>
            </div>
            {(stats.needs_template_count ?? 0) > 0 && (
              <p className="rounded bg-muted p-2 text-xs">
                {stats.needs_template_count} message(s) need an approved
                template — their 24h window closed before sending. Review them
                in the template manager.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
