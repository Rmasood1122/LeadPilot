"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { overrideFailedPasses, resumeStrategyErrorMessage } from "@/lib/api/strategies";
import { Button } from "@/components/ui/button";
import { overrideOffer, reasonOk, MIN_REASON_CHARS } from "@/lib/verificationReview";
import type { StrategyOut, VerificationPass } from "@/lib/api/types";

/** Shown only for needs_human_review. Lets the owner accept 1-3 failed checks
 *  as a recorded human decision. Never offered for Legal & compliance. */
export function OverridePassesPanel(
  { strategyId, status, log }: {
    strategyId: string;
    status: StrategyOut["status"];
    log: VerificationPass[];
  },
) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [ack, setAck] = useState(false);
  const offer = overrideOffer(log);

  const run = useMutation({
    mutationFn: (passNos: number[]) => overrideFailedPasses(strategyId, passNos, reason.trim()),
    onSuccess: () => {
      toast.success("Signed off. The strategy is now verified, with your decision recorded.");
      queryClient.invalidateQueries({ queryKey: ["strategy", strategyId] });
    },
    onError: (err) => toast.error(resumeStrategyErrorMessage(err)),
  });

  if (status !== "needs_human_review" || offer.kind === "none") return null;

  if (offer.kind === "blocked") {
    return (
      <div role="note" className="rounded border border-border p-3 text-sm text-muted-foreground">
        {offer.reason}
      </div>
    );
  }

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        Review and pass manually
      </Button>
    );
  }

  return (
    <div role="group" aria-label="Pass failed checks manually"
         className="space-y-3 rounded border border-warning bg-card p-4 text-sm">
      <p className="font-medium">
        You are passing {offer.passes.length === 1 ? "this check" : "these checks"} yourself,
        not the automated judge.
      </p>
      <ul className="space-y-1">
        {offer.passes.map((p) => (
          <li key={p.pass_no}>
            <span className="font-medium">#{p.pass_no} {p.name}</span>
            {p.fix_description && (
              <span className="block text-xs text-muted-foreground">
                Why it failed: {p.fix_description}
              </span>
            )}
          </li>
        ))}
      </ul>
      <label className="block text-xs">
        Why is this acceptable? (min {MIN_REASON_CHARS} characters, kept on record)
        <textarea
          className="mt-1 w-full rounded border border-border bg-background p-2 text-sm"
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          aria-label="Reason for passing manually"
        />
      </label>
      <label className="flex items-start gap-2 text-xs">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        I have checked these points myself. This is recorded as my decision, and the
        document is not independently verified.
      </label>
      <div className="flex gap-2">
        <Button size="sm"
                disabled={run.isPending || !ack || !reasonOk(reason)}
                onClick={() => run.mutate(offer.passes.map((p) => p.pass_no))}>
          {run.isPending ? "Saving..." : "Pass manually"}
        </Button>
        <Button variant="outline" size="sm" disabled={run.isPending}
                onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
