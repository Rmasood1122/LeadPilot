"use client";

/** The follow-up email a meeting outcome produced: review, edit, send.
 *
 * Never sends by itself. The model's draft is saved to Gmail as a DRAFT; the
 * user either presses Send here (confirmed) or sends from Gmail. When Gmail is
 * not connected or lacks the compose scope, the text is still shown and
 * copyable -- the outcome row keeps it precisely so that case loses nothing. */

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, ExternalLink, RefreshCw, Send } from "lucide-react";

import {
  editFollowupDraft,
  regenerateFollowupDraft,
  sendFollowup,
  type MeetingOutcome,
} from "@/lib/api/meetingPrep";
import { draftStatusInfo } from "@/lib/meeting-prep";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

export function FollowupDraftCard({
  outcome,
  onChange,
}: {
  outcome: MeetingOutcome;
  onChange?: (updated: MeetingOutcome) => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [subject, setSubject] = useState(outcome.followup_subject ?? "");
  const [body, setBody] = useState(outcome.followup_body ?? "");
  const [confirmSend, setConfirmSend] = useState(false);
  const info = draftStatusInfo(outcome.draft_status, outcome.draft_error);

  // A regenerate replaces the text; keep the inputs in step with the row.
  useEffect(() => {
    setSubject(outcome.followup_subject ?? "");
    setBody(outcome.followup_body ?? "");
  }, [outcome.followup_subject, outcome.followup_body]);

  const done = (updated: MeetingOutcome, message: string) => {
    queryClient.invalidateQueries({ queryKey: ["meeting-outcomes", outcome.lead_id] });
    onChange?.(updated);
    toast(message, "success");
  };
  const fail = (error: unknown) => toast((error as Error).message, "error");

  const save = useMutation({
    mutationFn: () => editFollowupDraft(outcome.id, subject.trim(), body.trim()),
    onSuccess: (u) => done(u, u.draft_status === "draft_saved" ? "Draft updated in Gmail" : "Changes saved"),
    onError: fail,
  });
  const regenerate = useMutation({
    mutationFn: () => regenerateFollowupDraft(outcome.id),
    onSuccess: (u) => done(u, "Follow-up rewritten"),
    onError: fail,
  });
  const send = useMutation({
    mutationFn: () => sendFollowup(outcome.id),
    onSuccess: (u) => done(u, "Follow-up sent"),
    onError: fail,
  });

  const dirty =
    subject.trim() !== (outcome.followup_subject ?? "") ||
    body.trim() !== (outcome.followup_body ?? "");
  const hasText = !!(outcome.followup_subject || outcome.followup_body);
  const sent = outcome.draft_status === "sent";

  return (
    <section
      aria-label="Follow-up email"
      className="space-y-3 rounded-lg border border-border bg-card p-4 text-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="font-medium">Follow-up email</h4>
        <Badge tone={info.tone}>{outcome.draft_status.replace(/_/g, " ")}</Badge>
      </div>
      <p className="text-muted-foreground">
        {sent && outcome.sent_at
          ? `Sent ${new Date(outcome.sent_at).toLocaleString()}.`
          : info.message}
      </p>

      {hasText && (
        <div className="space-y-2">
          <label className="block text-xs font-medium text-muted-foreground" htmlFor={`subj-${outcome.id}`}>
            Subject
          </label>
          <Input
            id={`subj-${outcome.id}`}
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            disabled={!info.canEdit || sent}
            maxLength={300}
          />
          <label className="block text-xs font-medium text-muted-foreground" htmlFor={`body-${outcome.id}`}>
            Body
          </label>
          <Textarea
            id={`body-${outcome.id}`}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            disabled={!info.canEdit || sent}
            rows={8}
            maxLength={6000}
          />
        </div>
      )}

      {!sent && (
        <div className="flex flex-wrap gap-2">
          {info.canEdit && hasText && (
            <Button size="sm" variant="outline" disabled={!dirty || save.isPending}
                    onClick={() => save.mutate()}>
              {save.isPending ? "Saving…" : "Save changes"}
            </Button>
          )}
          {outcome.draft_status !== "suppressed" && (
            <Button size="sm" variant="ghost" disabled={regenerate.isPending}
                    onClick={() => regenerate.mutate()}>
              <RefreshCw size={14} aria-hidden="true" />
              {regenerate.isPending ? "Rewriting…" : "Regenerate"}
            </Button>
          )}
          {hasText && (
            <Button size="sm" variant="ghost"
                    onClick={() => {
                      void navigator.clipboard?.writeText(`Subject: ${subject}\n\n${body}`);
                      toast("Copied to clipboard", "success");
                    }}>
              <Copy size={14} aria-hidden="true" /> Copy
            </Button>
          )}
          {outcome.draft_status === "draft_saved" && (
            <a
              href={outcome.gmail_drafts_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1 rounded border border-border px-3 text-xs font-medium hover:bg-muted"
            >
              <ExternalLink size={14} aria-hidden="true" /> Open Gmail drafts
            </a>
          )}
          {info.canSend && (
            <Button size="sm" disabled={dirty || send.isPending}
                    title={dirty ? "Save your changes first" : undefined}
                    onClick={() => setConfirmSend(true)}>
              <Send size={14} aria-hidden="true" /> {send.isPending ? "Sending…" : "Send now"}
            </Button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmSend}
        onClose={() => setConfirmSend(false)}
        onConfirm={() => {
          setConfirmSend(false);
          send.mutate();
        }}
        title="Send this follow-up?"
        body={`It will be sent from your Gmail account as "${subject}". This cannot be undone.`}
        confirmLabel="Send"
      />
    </section>
  );
}
