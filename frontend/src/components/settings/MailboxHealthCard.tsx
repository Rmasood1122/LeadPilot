"use client";

/** Part 1 Feature 4 — per-mailbox deliverability health.
 *
 *  The card sits beside the existing per-DOMAIN card, not in place of it: the
 *  domain answers "are my DNS records right and am I blocklisted?", the
 *  mailbox answers "is THIS sender in trouble, and what is the system doing
 *  about it right now?".
 *
 *  Every throttle and pause states its reason in words, because a sender who
 *  finds their campaign running slowly and cannot find out why will assume the
 *  product is broken. And the complaint rate is labelled a proxy wherever it
 *  appears — LeadPilot has no feedback-loop feed, and a number presented as
 *  something it is not is worse than no number. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, PlayCircle, RefreshCw } from "lucide-react";

import {
  getMailboxHealth,
  refreshMailboxHealth,
  resumeMailbox,
  type MailboxHealth,
} from "@/lib/api/trust";
import {
  authGaps,
  bandTone,
  fleetWarning,
  rateText,
  scoreText,
  sortForDisplay,
  stateLabel,
  stateTone,
  throttleExplanation,
} from "@/lib/mailboxHealth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function MailboxHealthCard() {
  const toast = useToast();
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["mailbox-health"],
    queryFn: getMailboxHealth,
  });
  const refresh = useMutation({
    mutationFn: refreshMailboxHealth,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mailbox-health"] });
      toast("Mailbox health updated", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const mailboxes = sortForDisplay(data?.mailboxes ?? []);
  const warning = fleetWarning(mailboxes);

  return (
    <Card aria-label="Mailbox health">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <div>
          <CardTitle className="text-sm">Mailbox health</CardTitle>
          {data && (
            <p className="text-xs text-muted-foreground">
              Throttled below {data.thresholds.throttle_below}, paused below{" "}
              {data.thresholds.pause_below}. Checked every four hours.
            </p>
          )}
        </div>
        <Button size="sm" variant="ghost" disabled={refresh.isPending}
                onClick={() => refresh.mutate()}>
          <RefreshCw size={14} aria-hidden="true" />
          {refresh.isPending ? "Checking…" : "Check now"}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <AsyncState isLoading={isLoading} error={error}
                    empty={!mailboxes.length}
                    emptyLabel="No sending mailbox connected yet.">
          {warning && (
            <p className="flex items-start gap-2 text-sm font-medium">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
              {warning}
            </p>
          )}
          <ul className="space-y-3">
            {mailboxes.map((mailbox) => (
              <MailboxRow key={mailbox.mailbox_ref} mailbox={mailbox} />
            ))}
          </ul>
          {data && <p className="text-xs text-muted-foreground">{data.complaint_note}</p>}
        </AsyncState>
      </CardContent>
    </Card>
  );
}

function MailboxRow({ mailbox }: { mailbox: MailboxHealth }) {
  const toast = useToast();
  const qc = useQueryClient();
  const resume = useMutation({
    mutationFn: () => resumeMailbox(mailbox.mailbox_ref),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mailbox-health"] });
      toast("Sending resumed", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const explanation = throttleExplanation(mailbox);
  const gaps = authGaps(mailbox);

  return (
    <li className="space-y-1 border-b border-border/40 pb-3 last:border-0 last:pb-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">{mailbox.address ?? mailbox.mailbox_ref}</span>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={bandTone(mailbox.band)} className="tabular-nums">
            {scoreText(mailbox.score)}{mailbox.score === null ? "" : "/100"}
          </Badge>
          <Badge tone={stateTone(mailbox.state)}>{stateLabel(mailbox.state)}</Badge>
          {mailbox.state === "paused" && (
            <Button size="sm" variant="ghost" disabled={resume.isPending}
                    onClick={() => resume.mutate()}>
              <PlayCircle size={14} aria-hidden="true" /> Resume
            </Button>
          )}
        </div>
      </div>

      {explanation && <p className="text-sm">{explanation}</p>}
      {mailbox.reasons.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4 text-xs text-muted-foreground">
          {mailbox.reasons.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}

      <p className="text-xs text-muted-foreground">
        Complaints {rateText(mailbox.complaint_rate)} (proxy) · bounces{" "}
        {rateText(mailbox.bounce_rate)} · {mailbox.sends_today} sent today,{" "}
        {mailbox.sends_7d} this week
        {gaps.length > 0 && <> · missing {gaps.join(", ")}</>}
      </p>
    </li>
  );
}
