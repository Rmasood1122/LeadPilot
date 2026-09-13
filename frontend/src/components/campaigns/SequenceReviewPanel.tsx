"use client";

/** Feature A7 — the pre-send red-team review for one sequence.
 *
 *  Shows what the review found (blocking issues first), lets a person re-run it
 *  after editing, and lets an owner/manager override blocking findings with a
 *  written reason. Launch (enroll/approve) is refused by the server while the
 *  current content is blocked, whatever this panel shows. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, ShieldCheck } from "lucide-react";

import { ApiError } from "@/lib/api/client";
import {
  getSequenceReview,
  overrideSequenceReview,
  runSequenceReview,
} from "@/lib/api/sequenceReview";
import {
  canLaunch,
  overrideReasonError,
  reviewHeadline,
  severityTone,
  sortFindings,
} from "@/lib/sequenceReview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/input";

export function SequenceReviewPanel({ sequenceId }: { sequenceId: string }) {
  const qc = useQueryClient();
  const key = ["sequence-review", sequenceId];
  const review = useQuery({
    queryKey: key,
    queryFn: () => getSequenceReview(sequenceId),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 2,
  });
  const run = useMutation({ mutationFn: () => runSequenceReview(sequenceId),
                            onSuccess: (data) => qc.setQueryData(key, data) });
  const [reason, setReason] = useState("");
  const override = useMutation({
    mutationFn: () => overrideSequenceReview(sequenceId, reason.trim()),
    onSuccess: (data) => { qc.setQueryData(key, data); setReason(""); },
  });

  const data = review.data;
  const notReviewed = review.error instanceof ApiError && review.error.status === 404;
  const ok = canLaunch(data);
  const reasonError = reason ? overrideReasonError(reason) : null;

  return (
    <section aria-label="Pre-send review" className="space-y-2 rounded border border-border p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-medium">
          {ok ? <ShieldCheck size={16} className="text-[rgb(var(--success))]" aria-hidden="true" />
              : <ShieldAlert size={16} className="text-[rgb(var(--warning))]" aria-hidden="true" />}
          {notReviewed ? "Not reviewed yet" : reviewHeadline(data)}
        </p>
        <Button size="sm" variant="outline" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? "Reviewing…" : data ? "Re-run review" : "Run review"}
        </Button>
      </div>

      {data && data.findings.length > 0 && (
        <ul className="space-y-1.5">
          {sortFindings(data.findings).map((f) => (
            <li key={f.id} className="flex items-start gap-2">
              <Badge tone={severityTone(f.severity)} className="shrink-0">{f.severity}</Badge>
              <span>
                {f.step_no ? <span className="font-medium">Step {f.step_no}: </span> : null}
                {f.message}
                {f.source === "model" && <span className="text-xs text-muted-foreground"> (AI)</span>}
              </span>
            </li>
          ))}
        </ul>
      )}

      {data?.status === "blocked" && data.is_current && (
        <form className="space-y-1" onSubmit={(e) => { e.preventDefault(); if (!overrideReasonError(reason)) override.mutate(); }}>
          <label htmlFor={`override-${sequenceId}`} className="text-xs text-muted-foreground">
            Owner or manager: launch anyway, with a reason (logged)
          </label>
          <Textarea id={`override-${sequenceId}`} value={reason} onChange={(e) => setReason(e.target.value)}
                    className="min-h-[60px]" />
          {reasonError && <p className="text-xs text-destructive">{reasonError}</p>}
          {override.isError && (
            <p role="alert" className="text-xs text-destructive">
              {override.error instanceof ApiError ? override.error.detail : "Override failed"}
            </p>
          )}
          <Button type="submit" size="sm" variant="destructive"
                  disabled={override.isPending || !!overrideReasonError(reason)}>
            Override and allow launch
          </Button>
        </form>
      )}
      {data?.status === "overridden" && data.override_reason && (
        <p className="text-xs text-muted-foreground">Override reason: “{data.override_reason}”</p>
      )}
    </section>
  );
}
