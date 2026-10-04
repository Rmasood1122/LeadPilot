"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { reverifyStrategy, resumeStrategyErrorMessage } from "@/lib/api/strategies";
import { Button } from "@/components/ui/button";
import type { StrategyOut } from "@/lib/api/types";

/** Only a strategy waiting for human review can be re-verified; the server
 *  refuses every other status. */
export function canReverify(status: StrategyOut["status"]): boolean {
  return status === "needs_human_review";
}

/** Parse the optional budget field. undefined = leave unchanged, null = invalid. */
export function parseBudget(raw: string): number | undefined | null {
  if (raw.trim() === "") return undefined;
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : null;
}

export function ReverifyStrategyButton({ strategy }: { strategy: StrategyOut }) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [budget, setBudget] = useState("");
  const [attempts, setAttempts] = useState("4");

  const parsedBudget = parseBudget(budget);
  const parsedAttempts = Number(attempts);
  const attemptsOk = Number.isInteger(parsedAttempts) && parsedAttempts >= 1 && parsedAttempts <= 5;

  const run = useMutation({
    mutationFn: () =>
      reverifyStrategy(strategy.id, {
        maxBudgetUsd: parsedBudget === null ? undefined : parsedBudget,
        maxAttempts: parsedAttempts,
      }),
    onSuccess: () => {
      setConfirming(false);
      toast.success("Verification restarted. Research is reused, not repeated.");
      queryClient.invalidateQueries({ queryKey: ["strategy", strategy.id] });
    },
    onError: (err) => toast.error(resumeStrategyErrorMessage(err)),
  });

  if (!canReverify(strategy.status)) return null;

  if (!confirming) {
    return (
      <Button variant="outline" size="sm" className="gap-1"
              onClick={() => setConfirming(true)}>
        <ShieldCheck size={14} aria-hidden="true" />
        Re-verify
      </Button>
    );
  }

  return (
    <div role="group" aria-label="Confirm re-verify"
         className="flex flex-wrap items-center gap-2 rounded border border-border p-2 text-xs">
      <span className="max-w-xs text-muted-foreground">
        Runs all 10 checks again on the finished research. This costs model
        spend, and it can still fail: nothing is marked verified unless every
        check passes.
      </span>
      <label className="flex items-center gap-1">
        Attempts per check
        <input
          className="w-12 rounded border border-border bg-background px-1 py-0.5"
          inputMode="numeric"
          value={attempts}
          onChange={(e) => setAttempts(e.target.value)}
          aria-label="Attempts per check (1 to 5)"
        />
      </label>
      <label className="flex items-center gap-1">
        New budget $
        <input
          className="w-16 rounded border border-border bg-background px-1 py-0.5"
          inputMode="decimal"
          placeholder="optional"
          value={budget}
          onChange={(e) => setBudget(e.target.value)}
          aria-label="New budget in dollars"
        />
      </label>
      <Button size="sm"
              disabled={run.isPending || parsedBudget === null || !attemptsOk}
              onClick={() => run.mutate()}>
        {run.isPending ? "Starting..." : "Confirm re-verify"}
      </Button>
      <Button variant="outline" size="sm" disabled={run.isPending}
              onClick={() => setConfirming(false)}>
        Cancel
      </Button>
    </div>
  );
}
