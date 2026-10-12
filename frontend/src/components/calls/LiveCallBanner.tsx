"use client";

/** Voice twin -- the app-wide "AI call live" banner with Take over
 *  (docs/features/voice-twin.md). Polls while the app is open; the push
 *  notification covers the app being closed. Quiet on any error. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PhoneCall } from "lucide-react";

import { getLiveCalls, takeOverCall } from "@/lib/api/voiceTwin";
import { liveCallText, liveCallsPollMs, showLiveBanner } from "@/lib/voiceTwin";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

export function LiveCallBanner() {
  const toast = useToast();
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["live-calls"],
    queryFn: getLiveCalls,
    refetchInterval: (query) => liveCallsPollMs(query.state.data),
    retry: false,
  });
  const takeOver = useMutation({
    mutationFn: takeOverCall,
    onSuccess: (r) => {
      toast(`Putting the call through to your phone (${r.to})`, "success");
      qc.invalidateQueries({ queryKey: ["live-calls"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  if (!data || !showLiveBanner(data.calls)) return null;
  return (
    <div className="no-print mb-4 space-y-2">
      {data.calls.map((call) => (
        <div key={call.id} role="status"
             className="flex flex-col gap-2 rounded border border-accent/50 bg-card p-3 text-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-2">
            <PhoneCall size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-accent" />
            <p className="font-medium">{liveCallText(call)}</p>
          </div>
          {call.can_take_over && (
            <Button size="sm" disabled={takeOver.isPending} onClick={() => takeOver.mutate(call.id)}>
              Take over
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}
