"use client";

/** Part 1 Feature 5 — the human review queue for high-risk sends.
 *
 *  Oldest first, because a queue that is worked newest-first leaves the stale
 *  messages at the bottom forever — and a held message that has waited three
 *  days is the one whose copy has quietly stopped being true ("this week",
 *  "following up on Tuesday").
 *
 *  Every row shows the copy as an EDITABLE field, not as read-only text. The
 *  point of a human gate is that the human can fix the message; forcing a
 *  reject-and-rewrite for a single bad line would make the queue something
 *  people clear rather than read. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Clock, X } from "lucide-react";

import {
  approveSendReview,
  listSendReviews,
  rejectSendReview,
} from "@/lib/api/sendReview";
import {
  canDecide,
  hasEdits,
  isStale,
  rejectNoteError,
  reviewHeadline,
  sortTriggers,
  triggerTone,
  waitingFor,
  type SendReviewItem,
} from "@/lib/sendReview";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

type QueueStatus = "pending" | "approved" | "rejected";

export function ReviewQueuePanel() {
  const [status, setStatus] = useState<QueueStatus>("pending");
  const { data, isLoading, error } = useQuery({
    queryKey: ["send-reviews", status],
    queryFn: () => listSendReviews(status),
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {data ? `${data.total} ${status}` : " "}
        </p>
        <div className="flex gap-2">
          {(["pending", "approved", "rejected"] as QueueStatus[]).map((value) => (
            <Button key={value} size="sm"
                    variant={status === value ? "default" : "ghost"}
                    onClick={() => setStatus(value)}>
              {value[0].toUpperCase() + value.slice(1)}
            </Button>
          ))}
        </div>
      </div>

      <AsyncState isLoading={isLoading} error={error}
                  empty={!data?.items.length}
                  emptyLabel={status === "pending"
                    ? "Nothing is waiting for approval."
                    : `No ${status} reviews.`}>
        <ul className="space-y-3">
          {data?.items.map((item) => <ReviewRow key={item.id} item={item} />)}
        </ul>
      </AsyncState>
    </div>
  );
}

function ReviewRow({ item }: { item: SendReviewItem }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [subject, setSubject] = useState(item.subject ?? "");
  const [body, setBody] = useState(item.body ?? "");
  const [note, setNote] = useState("");
  const [rejecting, setRejecting] = useState(false);

  const done = () => {
    qc.invalidateQueries({ queryKey: ["send-reviews"] });
    qc.invalidateQueries({ queryKey: ["send-reviews-count"] });
  };
  const approve = useMutation({
    mutationFn: () => approveSendReview(item.id, {
      note: note || undefined,
      ...(hasEdits(item, subject, body) ? { subject, body } : {}),
    }),
    onSuccess: () => { done(); toast("Approved — it will send on the next tick", "success"); },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const reject = useMutation({
    mutationFn: () => rejectSendReview(item.id, note),
    onSuccess: () => { done(); toast("Rejected — this message will not be sent", "info"); },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const noteError = rejecting ? rejectNoteError(note) : null;
  const editable = canDecide(item);

  return (
    <li>
      <Card>
        <CardHeader className="gap-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-sm">{reviewHeadline(item)}</CardTitle>
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <Clock size={12} aria-hidden="true" />
              {waitingFor(item)}
              {isStale(item) && <Badge tone="warning">Going stale</Badge>}
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {[item.lead?.title, item.lead?.company,
              item.step_no ? `step ${item.step_no}` : null, item.channel]
              .filter(Boolean).join(" · ")}
          </p>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <ul className="space-y-1" aria-label="Why this needs approval">
            {sortTriggers(item.triggers).map((trigger) => (
              <li key={trigger.code} className="flex flex-wrap items-baseline gap-2">
                <Badge tone={triggerTone(trigger.code)}>{trigger.label}</Badge>
                <span className="text-muted-foreground">{trigger.detail}</span>
              </li>
            ))}
          </ul>

          {editable ? (
            <div className="space-y-2">
              <div>
                <Label htmlFor={`subject-${item.id}`}>Subject</Label>
                <Input id={`subject-${item.id}`} value={subject}
                       onChange={(e) => setSubject(e.target.value)} />
              </div>
              <div>
                <Label htmlFor={`body-${item.id}`}>Message</Label>
                <Textarea id={`body-${item.id}`} rows={8} value={body}
                          onChange={(e) => setBody(e.target.value)} />
              </div>
              {hasEdits(item, subject, body) && (
                <p className="text-xs text-muted-foreground">
                  Approving sends your edit, not the original.
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-1">
              {item.subject && <p className="font-medium">{item.subject}</p>}
              <p className="whitespace-pre-line text-muted-foreground">{item.body}</p>
              {item.decision_note && (
                <p className="text-xs text-muted-foreground">Note: {item.decision_note}</p>
              )}
            </div>
          )}

          {editable && (
            <div className="space-y-2">
              <div>
                <Label htmlFor={`note-${item.id}`}>
                  Note {rejecting ? "(required to reject)" : "(optional)"}
                </Label>
                <Input id={`note-${item.id}`} value={note}
                       onChange={(e) => setNote(e.target.value)}
                       aria-invalid={noteError ? true : undefined} />
                {noteError && <p className="text-xs text-[rgb(var(--destructive))]">{noteError}</p>}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button disabled={approve.isPending} onClick={() => approve.mutate()}>
                  <Check size={16} aria-hidden="true" />
                  {hasEdits(item, subject, body) ? "Approve edit & send" : "Approve & send"}
                </Button>
                <Button variant="outline" disabled={reject.isPending}
                        onClick={() => {
                          if (!rejecting) { setRejecting(true); return; }
                          if (!rejectNoteError(note)) reject.mutate();
                        }}>
                  <X size={16} aria-hidden="true" />
                  {rejecting ? "Confirm reject" : "Reject"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </li>
  );
}
