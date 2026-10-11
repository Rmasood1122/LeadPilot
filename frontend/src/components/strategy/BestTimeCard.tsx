"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { getBestTime, setBestTime } from "@/lib/api/autopilot";
import { ApiError } from "@/lib/api/client";
import {
  bestTimeSavedMessage, DAY_NAMES, overrideError, timezoneNote, timezoneSources,
} from "@/lib/autopilot";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";

const CHANNEL_NAMES: Record<string, string> = {
  email: "Email", linkedin: "LinkedIn", whatsapp: "WhatsApp", phone: "Calls",
};

/** "Messages go out at ..." and why, with the person's own window
 *  (docs/features/autopilot-launch.md section 3.2). */
export function BestTimeCard({ strategyId }: { strategyId: string }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["best-time", strategyId],
    queryFn: () => getBestTime(strategyId),
    staleTime: 60_000,
  });
  const [editing, setEditing] = useState(false);
  const [days, setDays] = useState<number[]>([1, 2, 3]);
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("11:00");

  const save = useMutation({
    mutationFn: (window: { days: number[]; start: string; end: string } | null) =>
      setBestTime(strategyId, window),
    onSuccess: (view) => {
      queryClient.setQueryData(["best-time", strategyId], view);
      setEditing(false);
      toast.success(bestTimeSavedMessage(view));
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.detail : "Could not save the window."),
  });

  if (!data || !data.enabled) return null;
  const problem = overrideError(days, start, end);
  const tz = data.timezones;
  const sources = timezoneSources(tz);

  return (
    <section aria-label="Best time to send">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Best time to send</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <ul className="space-y-2">
            {data.channels.map((ch) => (
              <li key={ch.channel}>
                <span className="font-medium">{CHANNEL_NAMES[ch.channel] ?? ch.channel}:</span>{" "}
                {ch.summary}
                <span className="block text-xs text-muted-foreground">Why: {ch.reason}</span>
              </li>
            ))}
          </ul>
          {data.channels[0]?.priors_note && (
            <p className="text-xs text-muted-foreground">{data.channels[0].priors_note}</p>
          )}
          <p className="text-xs text-muted-foreground">
            Sending hours: {data.channels[0]?.sending_hours}, in each lead&apos;s local time.
            {sources ? ` Local time: ${sources}.` : ""}{" "}
            {timezoneNote(tz) ?? ""}
          </p>
          {editing ? (
            <div className="space-y-2 rounded border border-border p-2">
              <fieldset className="flex flex-wrap gap-2" aria-label="Days">
                {DAY_NAMES.map((name, i) => (
                  <label key={name} className="flex items-center gap-1">
                    <Checkbox checked={days.includes(i)}
                              onCheckedChange={(on) =>
                                setDays((d) => (on ? [...d, i].sort() : d.filter((x) => x !== i)))} />
                    {name}
                  </label>
                ))}
              </fieldset>
              <div className="flex flex-wrap items-center gap-2">
                <label>From <input className="w-20 rounded border border-border bg-background px-1"
                                   value={start} onChange={(e) => setStart(e.target.value)}
                                   aria-label="Window start (HH:MM)" /></label>
                <label>to <input className="w-20 rounded border border-border bg-background px-1"
                                 value={end} onChange={(e) => setEnd(e.target.value)}
                                 aria-label="Window end (HH:MM)" /></label>
                <span className="text-xs text-muted-foreground">each prospect&apos;s local time</span>
              </div>
              {problem && <p className="text-xs text-destructive">{problem}</p>}
              <div className="flex gap-2">
                <Button size="sm" disabled={!!problem || save.isPending}
                        onClick={() => save.mutate({ days, start, end })}>
                  Use my window
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                Choose my own window
              </Button>
              {data.override && (
                <Button size="sm" variant="ghost" disabled={save.isPending}
                        onClick={() => save.mutate(null)}>
                  Use the automatic best time
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
