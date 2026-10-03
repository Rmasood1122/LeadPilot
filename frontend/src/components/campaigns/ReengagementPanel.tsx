"use client";

/** Feature 5: the campaign's opt-in post-sequence re-engagement.
 *
 *  Off by default. Turning it on sends ONE email to each lead who finished
 *  this campaign's sequence without replying, unsubscribing or bouncing —
 *  capped per day and per week. The server enforces every rule; this panel
 *  shows the numbers so nobody switches it on without seeing its size. */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getReengagement, updateReengagement, type ReengagementPatch } from "@/lib/api/reengagement";
import { getCurrentWorkspace } from "@/lib/api/workspaces";
import { atLeast } from "@/lib/workspace";
import { AsyncState } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

export function ReengagementPanel({ strategyId }: { strategyId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const key = ["reengagement", strategyId];
  const { data, isLoading, error } = useQuery({
    queryKey: key,
    queryFn: () => getReengagement(strategyId),
    enabled: !!strategyId,
  });
  const { data: workspace } = useQuery({
    queryKey: ["workspace-current"],
    queryFn: getCurrentWorkspace,
  });
  const canEdit = atLeast(workspace?.role, "manager");

  const [draft, setDraft] = useState({ delay_days: 30, daily_cap: 10, weekly_cap: 25 });
  useEffect(() => {
    if (data) {
      setDraft({ delay_days: data.delay_days, daily_cap: data.daily_cap, weekly_cap: data.weekly_cap });
    }
  }, [data]);

  const save = useMutation({
    mutationFn: (body: ReengagementPatch) => updateReengagement(strategyId, body),
    onSuccess: (res) => {
      qc.setQueryData(key, res);
      toast(res.enabled ? "Re-engagement settings saved" : "Re-engagement is off", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const on = !!data?.enabled;
  const disabled = !data || !canEdit || save.isPending || (!on && !data.allowed);
  const dirty = !!data && (draft.delay_days !== data.delay_days
    || draft.daily_cap !== data.daily_cap || draft.weekly_cap !== data.weekly_cap);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-sm">Re-engagement</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">
            One final email to leads who finished this sequence without replying,
            unsubscribing or bouncing. Each lead is re-engaged at most once.
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={on}
          aria-label="Re-engagement"
          disabled={disabled}
          title={!canEdit ? "Needs a manager in this workspace" : undefined}
          onClick={() => save.mutate({ enabled: !on })}
          className={cn(
            "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-border transition-colors",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgb(var(--primary))] disabled:opacity-50",
            on ? "bg-[rgb(var(--primary))]" : "bg-muted",
          )}
        >
          <span
            className={cn(
              "inline-block h-4 w-4 rounded-full bg-card shadow transition-transform",
              on ? "translate-x-6" : "translate-x-1",
            )}
          />
        </button>
      </CardHeader>
      <CardContent className="space-y-4">
        <AsyncState isLoading={isLoading} error={error}>
          {data && (
            <>
              {!data.allowed && (
                <p className="text-sm text-muted-foreground">
                  Re-engagement is turned off for this deployment by an administrator.
                </p>
              )}
              <p className="text-sm">
                <span className="font-medium">
                  {data.eligible_now >= data.eligible_scan_limit
                    ? `${data.eligible_scan_limit}+`
                    : data.eligible_now}
                </span>{" "}
                <span className="text-muted-foreground">
                  lead(s) would qualify right now · sent today {data.sent_today} of{" "}
                  {data.effective.daily_cap} · this week {data.sent_this_week} of{" "}
                  {data.effective.weekly_cap}
                </span>
              </p>

              <div className="grid gap-3 sm:grid-cols-3">
                <div className="space-y-1">
                  <Label htmlFor="re-delay">Wait after last send (days)</Label>
                  <Input id="re-delay" type="number" disabled={!canEdit}
                         min={data.ceilings.min_delay_days} max={365} value={draft.delay_days}
                         onChange={(e) => setDraft({ ...draft, delay_days: Number(e.target.value) })} />
                  <p className="text-[11px] text-muted-foreground">At least {data.ceilings.min_delay_days}</p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="re-daily">Per day</Label>
                  <Input id="re-daily" type="number" disabled={!canEdit}
                         min={0} max={data.ceilings.daily_cap} value={draft.daily_cap}
                         onChange={(e) => setDraft({ ...draft, daily_cap: Number(e.target.value) })} />
                  <p className="text-[11px] text-muted-foreground">At most {data.ceilings.daily_cap}</p>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="re-weekly">Per 7 days</Label>
                  <Input id="re-weekly" type="number" disabled={!canEdit}
                         min={0} max={data.ceilings.weekly_cap} value={draft.weekly_cap}
                         onChange={(e) => setDraft({ ...draft, weekly_cap: Number(e.target.value) })} />
                  <p className="text-[11px] text-muted-foreground">At most {data.ceilings.weekly_cap}</p>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
                <span>
                  Email only. Every message still passes suppression, the send window
                  and your daily sending cap, and counts toward that cap.
                </span>
                <Button variant="outline" disabled={!canEdit || !dirty || save.isPending}
                        onClick={() => save.mutate(draft)}>
                  Save limits
                </Button>
              </div>
            </>
          )}
        </AsyncState>
      </CardContent>
    </Card>
  );
}
