"use client";

/** Part 1 Feature 1 — the positive reply rate, beside the raw reply rate.
 *
 *  Both numbers, always, because they answer different questions: the raw
 *  rate says "is the list responding?", the positive rate says "is the offer
 *  landing?". A campaign with a high raw rate and a low positive rate is
 *  getting through to people who are saying no.
 *
 *  The panel is honest about what it does not know: an unclassified backlog
 *  is shown, and a rate built on fewer than five human replies is labelled
 *  provisional rather than presented as a verdict. */

import { useQuery } from "@tanstack/react-query";

import { getReplyQuality } from "@/lib/api/replyIntent";
import {
  breakdownRows,
  intentTone,
  percent,
  qualityCaption,
  qualityIsProvisional,
} from "@/lib/replyIntent";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";

export function ReplyQualityPanel({ strategyId }: { strategyId?: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["reply-quality", strategyId ?? ""],
    queryFn: () => getReplyQuality(strategyId as string),
    enabled: Boolean(strategyId),
  });

  if (!strategyId) return null;
  const rows = breakdownRows(data);

  return (
    <Card aria-label="Reply quality">
      <CardHeader>
        <CardTitle className="text-sm">Reply quality</CardTitle>
        <p className="text-xs text-muted-foreground">{qualityCaption(data)}</p>
      </CardHeader>
      <CardContent>
        <AsyncState isLoading={isLoading} error={error}
                    empty={!!data && data.sent === 0}
                    emptyLabel="Nothing sent yet.">
          {data && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-6">
                <Metric label="Reply rate" value={percent(data.reply_rate)}
                        hint={`${data.replies} of ${data.sent} sent`} />
                <Metric label="Positive reply rate" value={percent(data.positive_reply_rate)}
                        hint={`${data.breakdown.interested} interested`}
                        provisional={qualityIsProvisional(data)} />
                <Metric label="Of replies understood" value={percent(data.positive_share)}
                        hint={`${data.classified} classified`} />
              </div>

              {rows.length > 0 && (
                <ul className="space-y-1" aria-label="Reply breakdown">
                  {rows.map((row) => (
                    <li key={row.label} className="flex items-center gap-2 text-sm">
                      <Badge tone={intentTone(row.label)}>{row.text}</Badge>
                      <span className="text-muted-foreground">
                        {row.count} · {percent(row.share)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {data.unclassified > 0 && (
                <p className="text-xs text-muted-foreground">
                  {data.unclassified} human {data.unclassified === 1 ? "reply has" : "replies have"}{" "}
                  no label yet, so the positive rate is a floor, not a final number.
                </p>
              )}
            </div>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}

function Metric({ label, value, hint, provisional }: {
  label: string; value: string; hint: string; provisional?: boolean;
}) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
      <p className="text-xs text-muted-foreground">
        {hint}
        {provisional && <span className="ml-1 italic">· provisional</span>}
      </p>
    </div>
  );
}
