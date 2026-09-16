"use client";

/** CRM — the reply inbox (Feature A3).
 *
 * Every reply on the account's leads, each with what the real-time scorer
 * decided: a genuine buyer or a machine (out-of-office, auto-responder, bot,
 * bounce), how confident it is, and — for genuine replies — how strong the
 * buying intent reads. The reasons are shown beside the scores, because a
 * score a person cannot check is a score they should not act on.
 *
 * The CRM layout supplies the header, tabs and live indicator. */

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Flame, RefreshCw } from "lucide-react";

import { listReplies, rescoreReply, type InboxQuery } from "@/lib/api/replies";
import { reclassifyReplyIntent } from "@/lib/api/replyIntent";
import { intentExplanation, intentLabel, intentTone } from "@/lib/replyIntent";
import {
  explainSignals,
  intentBand,
  kindLabel,
  kindTone,
  percent,
  type InboxReply,
} from "@/lib/authenticity";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { AsyncState } from "@/components/ui/skeleton";

const KIND_OPTIONS: { value: InboxQuery["kind"] | ""; label: string }[] = [
  { value: "", label: "All replies" },
  { value: "genuine", label: "Genuine only" },
  { value: "automated", label: "Automated (noise)" },
  { value: "out_of_office", label: "Out of office" },
  { value: "auto_responder", label: "Auto-responders" },
  { value: "bot", label: "Bots / no-reply" },
  { value: "bounce", label: "Bounces" },
];

const BAND_TEXT = { hot: "High intent", warm: "Some intent", cool: "Low intent", none: "" } as const;

export default function ReplyInboxPage() {
  const [kind, setKind] = useState<InboxQuery["kind"] | "">("");
  const [sort, setSort] = useState<"newest" | "intent">("intent");
  const query = useQuery({
    queryKey: ["crm-replies", kind, sort],
    queryFn: () => listReplies({ kind: kind || undefined, sort }),
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {query.data ? `${query.data.total} replies` : " "}
        </p>
        <div className="flex flex-wrap gap-2">
          <NativeSelect aria-label="Reply type" className="w-48" value={kind ?? ""}
                        onChange={(e) => setKind(e.target.value as InboxQuery["kind"] | "")}>
            {KIND_OPTIONS.map((o) => <option key={o.label} value={o.value ?? ""}>{o.label}</option>)}
          </NativeSelect>
          <NativeSelect aria-label="Sort" className="w-44" value={sort}
                        onChange={(e) => setSort(e.target.value as "newest" | "intent")}>
            <option value="intent">Highest intent first</option>
            <option value="newest">Newest first</option>
          </NativeSelect>
        </div>
      </div>

      <AsyncState isLoading={query.isLoading} error={query.error}
                  empty={!query.data?.items.length} emptyLabel="No replies match.">
        <ul className="space-y-3">
          {query.data?.items.map((reply) => <ReplyRow key={reply.reply_id} reply={reply} />)}
        </ul>
      </AsyncState>
    </div>
  );
}

function ReplyRow({ reply }: { reply: InboxReply }) {
  const qc = useQueryClient();
  const rescore = useMutation({
    mutationFn: () => rescoreReply(reply.reply_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["crm-replies"] }),
  });
  const reclassify = useMutation({
    mutationFn: () => reclassifyReplyIntent(reply.reply_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["crm-replies"] }),
  });
  const a = reply.authenticity;
  const band = intentBand(a);
  const reasons = a ? explainSignals(a.signals).slice(0, 4) : [];

  return (
    <li>
      <Card>
        <CardContent className="space-y-2 p-gutter">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              {reply.lead ? (
                <Link href={`/leads/detail?id=${reply.lead.id}`} className="font-medium hover:underline">
                  {reply.lead.full_name ?? reply.from_address}
                </Link>
              ) : (
                <span className="font-medium">{reply.from_address}</span>
              )}
              <p className="text-xs text-muted-foreground">
                {[reply.lead?.company, reply.channel,
                  reply.received_at ? new Date(reply.received_at).toLocaleString() : null]
                  .filter(Boolean).join(" · ")}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {/* Part 1 Feature 1: was this reply positive? */}
              <Badge tone={intentTone(reply.intent?.label)}
                     title={intentExplanation(reply.intent)}>
                {intentLabel(reply.intent?.label)}
              </Badge>
              <Badge tone={kindTone(a?.kind)} title={a ? `Confidence ${percent(a.confidence)}` : undefined}>
                {kindLabel(a?.kind)}{a ? ` · ${percent(a.confidence)}` : ""}
              </Badge>
              {band !== "none" && (
                <Badge tone={band === "hot" ? "primary" : "accent"}>
                  {band === "hot" && <Flame size={12} className="mr-1" aria-hidden="true" />}
                  {BAND_TEXT[band]} · {percent(a?.buyer_intent_score)}
                </Badge>
              )}
              {!a && (
                <Button size="sm" variant="ghost" disabled={rescore.isPending} onClick={() => rescore.mutate()}>
                  <RefreshCw size={14} aria-hidden="true" /> Score
                </Button>
              )}
              {!reply.intent?.label && (
                <Button size="sm" variant="ghost" disabled={reclassify.isPending}
                        onClick={() => reclassify.mutate()}>
                  <RefreshCw size={14} aria-hidden="true" /> Classify
                </Button>
              )}
            </div>
          </div>
          {reply.subject && <p className="text-sm font-medium">{reply.subject}</p>}
          <p className="whitespace-pre-line text-sm text-muted-foreground">{reply.body_preview}</p>
          {reply.intent?.reason && (
            <p className="text-xs text-muted-foreground">{intentExplanation(reply.intent)}</p>
          )}
          {reasons.length > 0 && (
            <p className="text-xs text-muted-foreground">Why: {reasons.join(" · ")}</p>
          )}
        </CardContent>
      </Card>
    </li>
  );
}
