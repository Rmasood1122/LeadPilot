"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { getAutopilot, setAutopilot, setAutopilotTemplate } from "@/lib/api/autopilot";
import { listTemplates } from "@/lib/api/campaigns";
import { ApiError } from "@/lib/api/client";
import {
  approvedTemplates, canEnable, optInBody, stateLabel, stateTone, unreachableNote,
} from "@/lib/autopilot";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";

const CHANNEL_NAMES: Record<string, string> = {
  email: "Email", linkedin: "LinkedIn", whatsapp: "WhatsApp",
};

/** Autopilot launch (docs/features/autopilot-launch.md). Turning it on needs
 *  the lawful-basis confirmation, never pre-ticked; the server enforces it
 *  (422 without it) and records who confirmed which text, when. */
export function AutopilotCard({ strategyId }: { strategyId: string }) {
  const queryClient = useQueryClient();
  const [confirmed, setConfirmed] = useState(false);
  const { data } = useQuery({
    queryKey: ["autopilot", strategyId],
    queryFn: () => getAutopilot(strategyId),
    refetchInterval: (q) => (q.state.data?.enabled ? 30_000 : false),
  });

  const change = useMutation({
    mutationFn: (enabled: boolean) =>
      setAutopilot(strategyId, optInBody(enabled, confirmed, data?.lawful_basis)),
    onSuccess: (view) => {
      setConfirmed(false);
      queryClient.setQueryData(["autopilot", strategyId], view);
      queryClient.invalidateQueries({ queryKey: ["send-diagnostics", strategyId] });
      toast.success(view.enabled ? "Autopilot is on." : "Autopilot is off.");
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.detail : "Could not change Autopilot."),
  });

  const usesWhatsApp = !!data && ("whatsapp" in (data.channels ?? {})
                                  || !!data.whatsapp_template_id);
  const { data: templates } = useQuery({
    queryKey: ["whatsapp-templates"],
    queryFn: listTemplates,
    enabled: usesWhatsApp && data?.can_change !== false,
    staleTime: 60_000,
  });
  const pickTemplate = useMutation({
    mutationFn: (id: string | null) => setAutopilotTemplate(strategyId, id),
    onSuccess: (view) => {
      queryClient.setQueryData(["autopilot", strategyId], view);
      toast.success(view.whatsapp_template_id
        ? "Autopilot will use that WhatsApp template."
        : "No WhatsApp template chosen: Autopilot's WhatsApp channel waits.");
    },
    onError: (err) =>
      toast.error(err instanceof ApiError ? err.detail : "Could not choose the template."),
  });

  if (!data || (!data.available && !data.enabled)) return null;
  const channels = Object.entries(data.channels ?? {});
  const unreachable = unreachableNote(data.unreachable);

  return (
    <section aria-label="Autopilot">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-sm">Autopilot</CardTitle>
          <Badge tone={data.enabled ? stateTone(data.state) : "default"}>
            {data.enabled ? stateLabel(data.state) : "Off"}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{data.lawful_basis.label}.</p>
          {data.approval_gap && (
            <p role="alert" className="text-destructive">
              {data.approval_gap}{" "}
              <Link className="underline" href="/send-approval">Set up daily send approval</Link>
            </p>
          )}
          {data.enabled ? (
            <>
              {data.state_reason && <p role="status">{data.state_reason}</p>}
              {unreachable && <p className="text-xs text-muted-foreground">{unreachable}</p>}
              {channels.length > 0 && (
                <ul className="space-y-1">
                  {channels.map(([name, ch]) => (
                    <li key={name} className="rounded border border-border p-2">
                      <span className="font-medium">{CHANNEL_NAMES[name] ?? name}</span>
                      {": "}
                      {ch.state === "launched"
                        ? `running (${ch.enrolled ?? 0} lead(s))`
                        : ch.reason ?? ch.state}
                      {ch.fix?.map((f) => (
                        <span key={f.title} className="block text-xs text-muted-foreground">
                          {f.fix}{" "}
                          {f.link && <Link className="underline" href={f.link}>Fix this</Link>}
                        </span>
                      ))}
                    </li>
                  ))}
                </ul>
              )}
              {usesWhatsApp && data.can_change !== false && (
                <label className="flex flex-wrap items-center gap-2 text-xs">
                  WhatsApp template Autopilot uses:
                  <select className="rounded border border-border bg-background px-1"
                          aria-label="WhatsApp template for Autopilot"
                          value={data.whatsapp_template_id ?? ""}
                          disabled={pickTemplate.isPending}
                          onChange={(e) => pickTemplate.mutate(e.target.value || null)}>
                    <option value="">None chosen (WhatsApp waits)</option>
                    {approvedTemplates(templates?.templates ?? []).map((t) => (
                      <option key={t.id} value={t.id}>{t.name} ({t.language})</option>
                    ))}
                  </select>
                </label>
              )}
              <p className="text-xs text-muted-foreground">
                Autopilot only contacts people its own lead searches find, never leads you
                added by hand. Every message still waits for your{" "}
                <Link className="underline" href="/send-approval">daily send approval</Link>{" "}
                and passes every compliance check.
              </p>
              {data.can_change !== false && (
                <Button variant="outline" size="sm" disabled={change.isPending}
                        onClick={() => change.mutate(false)}>
                  Turn off Autopilot
                </Button>
              )}
            </>
          ) : data.can_change === false ? (
            <p className="text-muted-foreground">
              Only the account owner or a manager can turn on Autopilot.
            </p>
          ) : (
            <>
              <label className="flex items-start gap-2">
                <Checkbox checked={confirmed} onCheckedChange={setConfirmed}
                          aria-label="Confirm I have a lawful basis to contact the people Autopilot finds" />
                <span>{data.lawful_basis.text}</span>
              </label>
              <Button size="sm"
                      disabled={!canEnable(confirmed, data.lawful_basis) || change.isPending}
                      onClick={() => change.mutate(true)}>
                Turn on Autopilot
              </Button>
            </>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
