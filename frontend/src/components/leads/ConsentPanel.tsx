"use client";

/** Part 1 Feature 9 — may we contact this person, and on what basis?
 *
 *  The panel answers the question that previously needed four tables: which
 *  channels are open, which are closed, and WHY each closed one is closed —
 *  because "no address on file" and "they asked us to stop" look identical in
 *  a product that only shows a red dot, and only one of them is a problem you
 *  can fix.
 *
 *  Withdrawing is one button, because a person asking to be left alone is
 *  making one statement about themselves, not setting four preferences. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldOff } from "lucide-react";

import { getLeadConsent, withdrawConsent } from "@/lib/api/consent";
import {
  activeNotes,
  channelLabel,
  channelStatusText,
  channelTone,
  consentHeadline,
  isFullySuppressed,
  kindLabel,
  kindTone,
  orderedChannels,
} from "@/lib/consent";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function ConsentPanel({ leadId }: { leadId: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [detail, setDetail] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["lead-consent", leadId],
    queryFn: () => getLeadConsent(leadId),
  });
  const withdraw = useMutation({
    mutationFn: () => withdrawConsent(leadId, "manual", detail || undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["lead-consent", leadId] });
      setAsking(false);
      toast("Suppressed on every channel", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const rows = orderedChannels(data);
  const notes = activeNotes(data);

  return (
    <Card aria-label="Consent and compliance">
      <CardHeader className="gap-1">
        <CardTitle className="text-sm">Can we contact them?</CardTitle>
        <p className="text-xs text-muted-foreground">{consentHeadline(data)}</p>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <AsyncState isLoading={isLoading} error={error}>
          {data && (
            <>
              <ul className="space-y-1" aria-label="Channels">
                {rows.map(({ channel, entry }) => (
                  <li key={channel} className="flex flex-wrap items-center gap-2">
                    <span className="w-20 shrink-0">{channelLabel(channel)}</span>
                    <Badge tone={channelTone(entry)}>{channelStatusText(entry)}</Badge>
                    {entry.identifier && (
                      <span className="truncate text-xs text-muted-foreground">
                        {entry.identifier}
                      </span>
                    )}
                  </li>
                ))}
              </ul>

              {notes.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
                  {notes.map((note) => <li key={note}>{note}</li>)}
                </ul>
              )}

              <p className="text-xs text-muted-foreground">
                Legal basis on file: {data.legal_basis}. A record of what was
                checked — not legal advice.
              </p>

              {!isFullySuppressed(data) && (
                <div className="space-y-2">
                  {asking && (
                    <div>
                      <Label htmlFor={`withdraw-${leadId}`}>
                        How did they ask? (optional, recorded in the ledger)
                      </Label>
                      <Input id={`withdraw-${leadId}`} value={detail}
                             onChange={(e) => setDetail(e.target.value)}
                             placeholder="e.g. asked me to stop on a call" />
                    </div>
                  )}
                  <Button size="sm" variant="outline" disabled={withdraw.isPending}
                          onClick={() => (asking ? withdraw.mutate() : setAsking(true))}>
                    <ShieldOff size={14} aria-hidden="true" />
                    {asking ? "Confirm — suppress everywhere" : "They asked us to stop"}
                  </Button>
                </div>
              )}

              {data.history.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Consent history
                  </p>
                  <ul className="mt-1 space-y-1 text-xs">
                    {data.history.slice(0, 8).map((event) => (
                      <li key={event.id} className="flex flex-wrap items-center gap-2">
                        <Badge tone={kindTone(event.kind)}>{kindLabel(event.kind)}</Badge>
                        <span className="text-muted-foreground">
                          {channelLabel(event.channel)} · {event.source}
                          {event.ts ? ` · ${new Date(event.ts).toLocaleDateString()}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}
