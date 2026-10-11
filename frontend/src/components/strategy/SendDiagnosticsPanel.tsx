"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { getSendDiagnostics } from "@/lib/api/autopilot";
import { diagnosticsHeadline, type DiagnosticReason } from "@/lib/autopilot";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

function Reason({ r }: { r: DiagnosticReason }) {
  return (
    <li className="rounded border border-border p-2">
      <span className={r.blocking ? "font-medium" : "text-muted-foreground"}>{r.title}</span>
      {r.detail && <span className="block text-xs text-muted-foreground">{r.detail}</span>}
      {(r.fix || r.link) && (
        <span className="block text-xs">
          {r.fix}{" "}
          {r.link && <Link className="underline" href={r.link}>Fix this</Link>}
        </span>
      )}
    </li>
  );
}

/** "Why isn't this sending?" -- every condition stopping this strategy's
 *  outreach, per channel, from the same checks the send path runs
 *  (docs/features/autopilot-launch.md section 3.3). */
export function SendDiagnosticsPanel({ strategyId }: { strategyId: string }) {
  const { data } = useQuery({
    queryKey: ["send-diagnostics", strategyId],
    queryFn: () => getSendDiagnostics(strategyId),
    staleTime: 30_000,
  });
  if (!data) return null;
  return (
    <section aria-label="Why isn't this sending?">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-sm">Why isn&apos;t this sending?</CardTitle>
          <Badge tone={data.sending ? "success" : "warning"}>
            {data.sending ? "Sending" : "Not sending"}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p role="status">{diagnosticsHeadline(data)}</p>
          {data.general.length > 0 && (
            <ul className="space-y-1">{data.general.map((r) => <Reason key={r.code} r={r} />)}</ul>
          )}
          {data.channels.map((ch) => (
            <div key={ch.channel} className="space-y-1">
              <p className="font-medium">
                {ch.label}: {ch.sending ? "nothing is stopping it" : "stopped"}
                {ch.next_send_at && (
                  <span className="text-xs text-muted-foreground">
                    {" "}(next message due {new Date(ch.next_send_at).toLocaleString()})
                  </span>
                )}
              </p>
              {ch.reasons.length > 0 && (
                <ul className="space-y-1">{ch.reasons.map((r) => <Reason key={r.code} r={r} />)}</ul>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </section>
  );
}
