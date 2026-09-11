"use client";

/** "Log Meeting Outcome": pick an outcome, paste notes, get a follow-up draft.
 *
 * Two stages in one dialog. First the form; then, once the outcome is logged,
 * the follow-up draft the server wrote, so the user reviews it where they
 * already are instead of hunting for it on another tab. The outcome itself is
 * committed server-side BEFORE the model is called, so closing the dialog at
 * any point after submit loses nothing. */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { logMeetingOutcome, type MeetingOutcome, type MeetingOutcomeKind } from "@/lib/api/meetingPrep";
import type { LeadOut } from "@/lib/api/types";
import { OUTCOME_OPTIONS, outcomeLabel, parseDealValue } from "@/lib/meeting-prep";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import { FollowupDraftCard } from "./FollowupDraftCard";

export function LogOutcomeDialog({
  lead,
  open,
  onClose,
}: {
  lead: LeadOut;
  open: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [outcome, setOutcome] = useState<MeetingOutcomeKind>("interested");
  const [notes, setNotes] = useState("");
  const [dealValue, setDealValue] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [draftFollowup, setDraftFollowup] = useState(true);
  const [result, setResult] = useState<MeetingOutcome | null>(null);

  const valueNumber = parseDealValue(dealValue);
  const valueInvalid = outcome === "closed_won" && dealValue.trim() !== "" && valueNumber === null;

  const submit = useMutation({
    mutationFn: () =>
      logMeetingOutcome(lead.id, {
        outcome,
        notes: notes.trim() || null,
        deal_value: outcome === "closed_won" ? valueNumber : null,
        currency: currency.trim().toUpperCase() || "USD",
        generate_followup: draftFollowup,
      }),
    onSuccess: (row) => {
      setResult(row);
      for (const key of [["lead", lead.id], ["leads"], ["meeting-outcomes", lead.id],
                         ["meeting-prep", lead.id], ["deals"]]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
      toast(`Logged: ${outcomeLabel(row.outcome)}`, "success");
    },
    onError: (error) => toast((error as Error).message, "error"),
  });

  const close = () => {
    setResult(null);
    setNotes("");
    setDealValue("");
    onClose();
  };

  return (
    <Modal open={open} onClose={close} title="Log meeting outcome" className="max-w-2xl">
      {result ? (
        <div className="space-y-4 text-sm">
          <p>
            <span className="font-medium">{outcomeLabel(result.outcome)}</span>{" "}
            logged. Lead moved from{" "}
            <span className="font-mono">{result.previous_status ?? "—"}</span> to{" "}
            <span className="font-mono">{result.new_status}</span>
            {result.deal_id ? " and a won deal was created." : "."}
          </p>
          {result.draft_status !== "pending" && (
            <FollowupDraftCard outcome={result} onChange={setResult} />
          )}
          <div className="flex justify-end">
            <Button onClick={close}>Done</Button>
          </div>
        </div>
      ) : (
        <form
          className="space-y-4 text-sm"
          onSubmit={(e) => {
            e.preventDefault();
            if (!valueInvalid) submit.mutate();
          }}
        >
          <fieldset className="space-y-2">
            <legend className="mb-1 font-medium">How did it go?</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {OUTCOME_OPTIONS.map((option) => (
                <label
                  key={option.value}
                  className={cn(
                    "flex cursor-pointer flex-col gap-0.5 rounded border p-3 transition-colors",
                    outcome === option.value
                      ? "border-[rgb(var(--primary))] bg-muted"
                      : "border-border hover:bg-muted",
                  )}
                >
                  <span className="flex items-center gap-2 font-medium">
                    <input
                      type="radio"
                      name="outcome"
                      value={option.value}
                      checked={outcome === option.value}
                      onChange={() => setOutcome(option.value)}
                    />
                    {option.label}
                  </span>
                  <span className="text-xs text-muted-foreground">{option.hint}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {outcome === "closed_won" && (
            <div className="grid grid-cols-[1fr_6rem] gap-2">
              <div>
                <label htmlFor="deal-value" className="mb-1 block text-xs font-medium text-muted-foreground">
                  Deal value
                </label>
                <Input
                  id="deal-value"
                  inputMode="decimal"
                  placeholder="4,500"
                  value={dealValue}
                  onChange={(e) => setDealValue(e.target.value)}
                  aria-invalid={valueInvalid}
                />
                {valueInvalid && (
                  <p className="mt-1 text-xs text-destructive">Enter a number, e.g. 4500 or 4,500.50</p>
                )}
              </div>
              <div>
                <label htmlFor="deal-currency" className="mb-1 block text-xs font-medium text-muted-foreground">
                  Currency
                </label>
                <Input
                  id="deal-currency"
                  maxLength={3}
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                />
              </div>
            </div>
          )}

          <div>
            <label htmlFor="meeting-notes" className="mb-1 block font-medium">
              Meeting notes
            </label>
            <Textarea
              id="meeting-notes"
              rows={6}
              maxLength={20000}
              placeholder="What they said, what was agreed, what's still open. The follow-up is written from these — it won't invent commitments that aren't here."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={draftFollowup}
              onChange={(e) => setDraftFollowup(e.target.checked)}
            />
            Draft a follow-up email and save it to Gmail for me to review
          </label>

          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={close}>Cancel</Button>
            <Button type="submit" disabled={submit.isPending || valueInvalid}>
              {submit.isPending
                ? draftFollowup ? "Logging and drafting…" : "Logging…"
                : "Log outcome"}
            </Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
