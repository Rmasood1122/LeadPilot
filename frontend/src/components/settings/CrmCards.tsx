"use client";

/** Feature Group 4: HubSpot and Salesforce two-way sync. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  crmAuthUrl, disconnectCrm, getCrm, syncCrm, updateCrmSettings,
  type CrmProvider, type CrmStatus,
} from "@/lib/api/ecosystem";
import { AsyncState } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const LABELS: Record<CrmProvider, { name: string; records: string }> = {
  hubspot: { name: "HubSpot", records: "contacts and deals" },
  salesforce: { name: "Salesforce", records: "leads and opportunities" },
};

function when(iso?: string | null): string {
  return iso ? new Date(iso).toLocaleString() : "never";
}

export function CrmCards() {
  const { data, isLoading, error } = useQuery({ queryKey: ["crm-integrations"], queryFn: getCrm });
  return (
    <AsyncState isLoading={isLoading} error={error}>
      <div className="space-y-3">
        {(data ?? []).map((s) => <CrmCard key={s.provider} status={s} />)}
      </div>
    </AsyncState>
  );
}

function CrmCard({ status }: { status: CrmStatus }) {
  const qc = useQueryClient();
  const toast = useToast();
  const p = status.provider;
  const label = LABELS[p];
  const refresh = () => qc.invalidateQueries({ queryKey: ["crm-integrations"] });
  const fail = (e: unknown) => toast((e as Error).message, "error");

  const connect = async () => {
    try {
      window.location.href = (await crmAuthUrl(p)).auth_url;
    } catch (e) {
      fail(e);
    }
  };
  const sync = useMutation({
    mutationFn: () => syncCrm(p),
    onSuccess: () => toast(`${label.name} sync queued`, "info"),
    onError: fail,
  });
  const settings = useMutation({
    mutationFn: (on: boolean) => updateCrmSettings(p, { sync_new_leads: on }),
    onSuccess: refresh,
    onError: fail,
  });
  const disconnect = useMutation({
    mutationFn: () => disconnectCrm(p),
    onSuccess: () => { refresh(); toast(`${label.name} disconnected`, "info"); },
    onError: fail,
  });

  return (
    <Card>
      <CardContent className="space-y-2 p-gutter">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">
              {label.name}
              {status.connected && (
                <span className={cn(
                  "ml-2 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                  status.status === "error"
                    ? "bg-[rgb(var(--destructive)/0.12)] text-[rgb(var(--destructive))]"
                    : "bg-[rgb(var(--success)/0.12)] text-[rgb(var(--success))]",
                )}>
                  {status.status === "error" ? "needs attention" : "connected"}
                </span>
              )}
            </p>
            <p className="text-xs text-muted-foreground">
              {status.connected
                ? `${status.account_name ?? status.account_id ?? ""} · ${status.linked_leads ?? 0} leads, ` +
                  `${status.linked_deals ?? 0} deals linked · last push ${when(status.last_push_at)}, ` +
                  `last pull ${when(status.last_pull_at)}`
                : `Two-way sync of engaged leads and deals with your ${label.name} ${label.records}.`}
            </p>
          </div>
          {status.connected ? (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => sync.mutate()} disabled={sync.isPending}>
                Sync now
              </Button>
              <Button size="sm" variant="outline" onClick={() => disconnect.mutate()}
                      disabled={disconnect.isPending}>
                Disconnect
              </Button>
            </div>
          ) : (
            <Button size="sm" onClick={connect} disabled={!status.configured}>Connect</Button>
          )}
        </div>
        {!status.configured && !status.connected && (
          <p className="text-xs text-muted-foreground">
            An admin must add the {label.name} app under Admin › Integrations first.
          </p>
        )}
        {status.connected && status.last_error && (
          <p role="alert" className="text-xs text-[rgb(var(--destructive))]">
            Last error: {status.last_error}
            {status.status === "error" ? " — reconnect to restore the sync." : ""}
          </p>
        )}
        {status.connected && (
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={!!status.settings?.sync_new_leads}
              disabled={settings.isPending}
              onChange={(e) => settings.mutate(e.target.checked)}
            />
            Also push every verified lead (by default only leads that replied or further)
          </label>
        )}
      </CardContent>
    </Card>
  );
}
