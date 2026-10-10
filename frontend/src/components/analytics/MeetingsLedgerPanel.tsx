"use client";

/** F08 — the meetings-per-dollar ledger, on Revenue & ROI.
 *
 *  Per campaign: what it cost ÷ qualified conversations, booked meetings and
 *  held meetings, and how sure we are that the campaign earned each booking
 *  (the attribution ledger's method — a reply is a fact, last-touch is a
 *  guess, pending is not attributed yet). CSV and PDF export.
 *
 *  Behind `meetings_ledger_enabled` (default off): a 409 renders one quiet
 *  line, not an error. */

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download } from "lucide-react";

import { downloadMeetingsLedger, getMeetingsLedger } from "@/lib/api/meetingsLedger";
import {
  certaintyCaveat,
  exportFilename,
  infrastructureLabel,
  isDisabledError,
  methodMixLabel,
  reconciliationLabel,
  type LedgerExportFormat,
  type LedgerExportView,
  type LedgerQuery,
} from "@/lib/meetingsLedger";
import { formatMoney } from "@/lib/revenue";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { StatTile } from "@/components/crm/dashboard/primitives";
import { cn } from "@/lib/utils";

export function MeetingsLedgerPanel({ dateFrom, dateTo }: { dateFrom: string; dateTo: string }) {
  const toast = useToast();
  const query: LedgerQuery = { dateFrom, dateTo };
  const { data, isLoading, error } = useQuery({
    queryKey: ["meetings-ledger", dateFrom, dateTo],
    queryFn: () => getMeetingsLedger(query),
    retry: (count, err) => !isDisabledError(err) && count < 2,
  });
  const download = useMutation({
    mutationFn: async ({ format, view }: { format: LedgerExportFormat; view: LedgerExportView }) => {
      const blob = await downloadMeetingsLedger(query, format, view);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = exportFilename(query, format, view);
      link.click();
      URL.revokeObjectURL(url);
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  if (isDisabledError(error)) {
    return (
      <Card aria-label="Meetings per dollar">
        <CardContent className="p-gutter text-sm text-muted-foreground">
          The meetings-per-dollar ledger is off. An administrator can turn it on in
          Admin › System Settings (<code>meetings_ledger_enabled</code>).
        </CardContent>
      </Card>
    );
  }

  const currency = data?.currency ?? "USD";
  const money = (cents: number | null) => formatMoney(cents, currency);
  const caveat = certaintyCaveat(data?.totals);
  const rec = data ? reconciliationLabel(data.reconciliation) : null;

  return (
    <Card aria-label="Meetings per dollar">
      <CardHeader className="flex flex-row flex-wrap items-start justify-between gap-2">
        <div>
          <CardTitle className="text-sm">Meetings per dollar</CardTitle>
          <p className="text-xs text-muted-foreground">
            What each qualified conversation, booked meeting and held meeting cost, per campaign.
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          {([["csv", "campaigns", "CSV"], ["csv", "events", "CSV (events)"], ["pdf", "campaigns", "PDF"]] as const)
            .map(([format, view, label]) => (
              <Button key={`${format}-${view}`} size="sm" variant="outline"
                      disabled={!data || download.isPending}
                      onClick={() => download.mutate({ format, view })}>
                <Download className="mr-1 h-3.5 w-3.5" aria-hidden />
                {label}
              </Button>
            ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <AsyncState isLoading={isLoading} error={error}>
          {data && (
            <>
              {caveat && (
                <div role="note"
                     className="flex items-start gap-2 rounded border border-warning bg-card p-3 text-xs text-muted-foreground">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[rgb(var(--warning))]" aria-hidden />
                  {caveat}
                </div>
              )}

              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <StatTile label="Total cost" value={money(data.totals.total_cost_cents)}
                          sub={`${data.totals.sends} sends`} />
                <StatTile label="Cost / qualified conversation"
                          value={money(data.totals.cost_per_qualified_conversation_cents)}
                          sub={`${data.totals.qualified_conversations} qualified`} />
                <StatTile label="Cost / meeting booked"
                          value={money(data.totals.cost_per_meeting_booked_cents)}
                          sub={`${data.totals.meetings_booked} booked · ${methodMixLabel(data.totals.booked_by_method)}`} />
                <StatTile label="Cost / meeting held"
                          value={money(data.totals.cost_per_meeting_held_cents)}
                          sub={`${data.totals.meetings_held} held`} />
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[860px] text-sm" aria-label="Meetings per dollar by campaign">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="py-1.5 font-medium">Campaign</th>
                      <th className="text-right font-medium">Cost</th>
                      <th className="text-right font-medium">Qualified</th>
                      <th className="text-right font-medium">Booked</th>
                      <th className="text-right font-medium">Held</th>
                      <th className="text-right font-medium">/ qualified</th>
                      <th className="text-right font-medium">/ booked</th>
                      <th className="text-right font-medium">/ held</th>
                      <th className="pl-3 font-medium">Booked — attribution</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.campaigns.map((c) => (
                      <tr key={c.strategy_id} className="border-b border-border/50 tabular-nums">
                        <td className="py-1.5 font-medium">{c.name}</td>
                        <td className="text-right"
                            title={`AI ${money(c.ai_cost_cents)} · Data ${money(c.data_cost_cents)} · `
                                   + `Other ${money(c.other_recorded_cost_cents)} · Shared ${money(c.shared_cost_cents)} · `
                                   + `Platform ${money(c.platform_fee_cents)} · Infrastructure ${money(c.infrastructure_cost_cents)}`}>
                          {money(c.total_cost_cents)}
                        </td>
                        <td className="text-right">{c.qualified_conversations}</td>
                        <td className="text-right">{c.meetings_booked}</td>
                        <td className="text-right">{c.meetings_held}</td>
                        <td className="text-right">{money(c.cost_per_qualified_conversation_cents)}</td>
                        <td className="text-right">{money(c.cost_per_meeting_booked_cents)}</td>
                        <td className="text-right">{money(c.cost_per_meeting_held_cents)}</td>
                        <td className="pl-3 text-xs text-muted-foreground">{methodMixLabel(c.booked_by_method)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="space-y-1 text-[11px] text-muted-foreground">
                <p>
                  Cost = AI (metered model spend, AI-call minutes, recorded AI costs) + recorded data and
                  other costs + a share of account-wide costs by sends + pay-per-meeting fees + infrastructure.
                  {" "}{infrastructureLabel(data.infrastructure)}
                </p>
                {data.totals.unallocated_cost_cents > 0 && (
                  <p>
                    Includes {money(data.totals.unallocated_cost_cents)} of account-wide cost not allocated to a
                    campaign (no sends in the period).
                  </p>
                )}
                {rec && (
                  <p className={cn(!rec.ok && "text-[rgb(var(--destructive))]")}>{rec.text}</p>
                )}
              </div>
            </>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}
