"use client";

/** Profile → Plan: the plan, how it is billed, what happens next, and the
 *  online CANCEL PLAN button (docs/features/annual-billing.md, "Online
 *  cancel"). Cancelling calls POST /billing/cancel: a live monthly or annual
 *  plan stops renewing and stays until the end of the paid period; a PAST-DUE
 *  one ends now and its unpaid invoice is voided; pay per meeting (and stub
 *  mode) ends now. The confirm step says which (cancelConsequence). One button, one confirm step — as easy
 *  as signing up. */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";
import { billingApi } from "@/lib/api/billing";
import { canCancel, cancelConsequence, subscriptionSummary } from "@/lib/pricing";
import { canUpgrade, planLabel } from "@/lib/profile";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function PlanCard({ plan }: { plan: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const overview = useQuery({ queryKey: ["billing", "overview"], queryFn: billingApi.overview,
                              retry: false });
  const sub = overview.data?.subscription ?? null;
  const summary = subscriptionSummary(sub, overview.data?.usage?.currency ?? "usd");

  const cancel = useMutation({
    mutationFn: billingApi.cancel,
    onSuccess: () => {
      setConfirming(false);
      setMessage({ ok: true, text: "Your plan is cancelled. It will not renew." });
      void qc.invalidateQueries({ queryKey: ["billing", "overview"] });
      void qc.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (err) => setMessage({
      ok: false, text: err instanceof ApiError ? err.detail : "Could not cancel. Try again.",
    }),
  });

  return (
    <Card>
      <CardHeader><CardTitle>Plan</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>You are on the <strong>{planLabel(plan)}</strong> plan.</p>
        {summary && <p className="text-muted-foreground" data-testid="plan-summary">{summary}</p>}
        {sub?.needs_support && (
          <p role="status" className="rounded-lg border border-border p-2">
            A second plan was started while your annual plan was already paid. Both are kept
            and the new one will not renew; our team will contact you about a refund or a
            change. Nothing is lost.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {canUpgrade(plan)
            ? <Button onClick={() => router.push("/pricing")}>Upgrade plan</Button>
            : <p className="text-muted-foreground">This is the highest plan.</p>}
          {canCancel(sub) && !confirming && (
            <Button variant="outline" onClick={() => { setMessage(null); setConfirming(true); }}>
              Cancel plan
            </Button>
          )}
        </div>
        {confirming && sub && (
          <div role="alertdialog" aria-label="Confirm cancellation"
               className="space-y-2 rounded-lg border border-border p-3">
            <p>{cancelConsequence(sub)}</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="destructive" disabled={cancel.isPending}
                      onClick={() => cancel.mutate()}>
                Yes, cancel my plan
              </Button>
              <Button variant="ghost" onClick={() => setConfirming(false)}>Keep my plan</Button>
            </div>
          </div>
        )}
        {message && (
          <p role={message.ok ? "status" : "alert"}
             className={message.ok ? "" : "text-red-600"}>{message.text}</p>
        )}
      </CardContent>
    </Card>
  );
}
