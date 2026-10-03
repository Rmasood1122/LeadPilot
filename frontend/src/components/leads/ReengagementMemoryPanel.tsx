"use client";

/** Part 1 Feature 7 — the dated return visits a prospect's "not now" created.
 *
 *  The panel exists to make one thing impossible to forget: the prospect told
 *  you WHEN. It shows their reason in their own words, whether the date came
 *  from them or from our default (those are different promises), and the
 *  opening line the return message should use — so a person can sanity-check
 *  it, or write it themselves. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, X } from "lucide-react";

import {
  cancelReengagementPlan,
  getLeadReengagementPlans,
  rescheduleReengagementPlan,
  type ReengagementPlan,
} from "@/lib/api/reengagement";
import {
  cancelReasonError,
  dueLabel,
  isDue,
  reasonTone,
  sortPlans,
  statusTone,
  suggestedOpener,
  whyThisDate,
} from "@/lib/reengagementMemory";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function ReengagementMemoryPanel({ leadId }: { leadId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["lead-reengagement-plans", leadId],
    queryFn: () => getLeadReengagementPlans(leadId),
  });
  const plans = sortPlans(data ?? []);

  return (
    <Card aria-label="Re-engagement memory">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <CalendarClock size={16} aria-hidden="true" /> Come back to this prospect
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <AsyncState isLoading={isLoading} error={error} empty={!plans.length}
                    emptyLabel="No “not now” on file for this prospect.">
          <ul className="space-y-3">
            {plans.map((plan) => <PlanRow key={plan.id} plan={plan} leadId={leadId} />)}
          </ul>
        </AsyncState>
      </CardContent>
    </Card>
  );
}

function PlanRow({ plan, leadId }: { plan: ReengagementPlan; leadId: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [due, setDue] = useState(plan.stated_return_on ?? "");
  const [reason, setReason] = useState("");
  const [cancelling, setCancelling] = useState(false);

  const done = (message: string) => {
    qc.invalidateQueries({ queryKey: ["lead-reengagement-plans", leadId] });
    qc.invalidateQueries({ queryKey: ["reengagement-plans"] });
    toast(message, "success");
  };
  const reschedule = useMutation({
    mutationFn: () => rescheduleReengagementPlan(plan.id, due),
    onSuccess: () => done("Moved"),
    onError: (e) => toast((e as Error).message, "error"),
  });
  const cancel = useMutation({
    mutationFn: () => cancelReengagementPlan(plan.id, reason),
    onSuccess: () => done("Cancelled"),
    onError: (e) => toast((e as Error).message, "error"),
  });

  const open = plan.status === "scheduled" || plan.status === "due";
  const reasonError = cancelling ? cancelReasonError(reason) : null;

  return (
    <li className="space-y-2 border-b border-border/40 pb-3 last:border-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={reasonTone(plan.reason_kind)}>{plan.reason_label}</Badge>
        <Badge tone={statusTone(plan.status)}>{plan.status}</Badge>
        <span className={isDue(plan) ? "font-medium" : "text-muted-foreground"}>
          {dueLabel(plan)}
        </span>
        {plan.date_from_prospect && <Badge tone="success">Their date</Badge>}
      </div>

      {plan.reason_text && <p>“{plan.reason_text}”</p>}
      <p className="text-xs text-muted-foreground">{whyThisDate(plan)}</p>
      {open && (
        <p className="text-xs text-muted-foreground">
          Suggested opener: {suggestedOpener(plan)}
        </p>
      )}
      {plan.cancelled_reason && (
        <p className="text-xs text-muted-foreground">
          Cancelled: {plan.cancelled_reason}
        </p>
      )}

      {open && (
        <div className="flex flex-wrap items-end gap-2">
          <div>
            <Label htmlFor={`due-${plan.id}`}>Move to</Label>
            <Input id={`due-${plan.id}`} type="date" value={due}
                   onChange={(e) => setDue(e.target.value)} className="w-40" />
          </div>
          <Button size="sm" variant="outline" disabled={!due || reschedule.isPending}
                  onClick={() => reschedule.mutate()}>
            Move
          </Button>
          <div className="flex-1">
            <Label htmlFor={`cancel-${plan.id}`}>
              {cancelling ? "Why never?" : " "}
            </Label>
            {cancelling && (
              <Input id={`cancel-${plan.id}`} value={reason}
                     onChange={(e) => setReason(e.target.value)}
                     aria-invalid={reasonError ? true : undefined} />
            )}
            {reasonError && (
              <p className="text-xs text-[rgb(var(--destructive))]">{reasonError}</p>
            )}
          </div>
          <Button size="sm" variant="ghost" disabled={cancel.isPending}
                  onClick={() => {
                    if (!cancelling) { setCancelling(true); return; }
                    if (!cancelReasonError(reason)) cancel.mutate();
                  }}>
            <X size={14} aria-hidden="true" />
            {cancelling ? "Confirm never" : "Never"}
          </Button>
        </div>
      )}
    </li>
  );
}
