"use client";

/** Admin > Integrations: deployment-wide API keys and OAuth app credentials.
 *
 * Every value typed here goes to TokenStore (Fernet-encrypted) and NEVER comes
 * back: the API reports which keys are set, not what they are. That is why an
 * input for a key that is already set is empty with a "set" placeholder rather
 * than showing a masked value -- a mask still leaks length and prefix. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  clearSystemIntegration,
  listSystemIntegrations,
  setSystemIntegration,
  type SystemIntegration,
} from "@/lib/api/systemAdmin";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function AdminIntegrationsPage() {
  const query = useQuery({
    queryKey: ["admin", "integrations"],
    queryFn: listSystemIntegrations,
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Integrations</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Deployment-wide credentials. Stored encrypted; values are never shown again after saving.
          Users connect their own Slack, HubSpot and Salesforce accounts from Settings — these are
          the app credentials those connections are made with.
        </p>
      </div>
      {query.isLoading && <div className="text-muted-foreground">Loading…</div>}
      {query.error && <div className="text-destructive">{(query.error as Error).message}</div>}
      <div className="grid gap-4 xl:grid-cols-2">
        {(query.data ?? []).map((integration) => (
          <ProviderCard key={integration.provider} integration={integration} />
        ))}
      </div>
    </div>
  );
}

function ProviderCard({ integration }: { integration: SystemIntegration }) {
  const qc = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>({});
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "integrations"] });

  const save = useMutation({
    mutationFn: (payload: Record<string, string>) =>
      setSystemIntegration(integration.provider, payload),
    onSuccess: () => {
      setValues({});
      refresh();
      toast.success(`${integration.label} saved`);
    },
    onError: (e) => toast.error((e as Error).message),
  });
  const clear = useMutation({
    mutationFn: () => clearSystemIntegration(integration.provider),
    onSuccess: () => {
      refresh();
      toast.success(`${integration.label} cleared`);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const pending = Object.fromEntries(
    Object.entries(values).filter(([, v]) => v.trim() !== ""),
  );
  const anySet = integration.keys.some((k) => k.is_set);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>{integration.label}</CardTitle>
          <Badge tone={integration.configured ? "success" : anySet ? "warning" : "default"}>
            {integration.configured ? "Configured" : anySet ? "Incomplete" : "Not set"}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{integration.purpose}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {integration.keys.map(({ key, is_set }) => (
          <div key={key} className="flex items-end gap-2">
            <div className="flex-1">
              <label htmlFor={`${integration.provider}-${key}`}
                     className="mb-1 block font-mono text-xs text-muted-foreground">
                {key}
              </label>
              <Input
                id={`${integration.provider}-${key}`}
                type="password"
                autoComplete="off"
                placeholder={is_set ? "Set — type a new value to replace it" : "Not set"}
                value={values[key] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
              />
            </div>
            {is_set && (
              <Button variant="ghost" size="sm" disabled={save.isPending}
                      onClick={() => save.mutate({ [key]: "" })}>
                Clear
              </Button>
            )}
          </div>
        ))}
        <div className="flex justify-between gap-2 pt-1">
          <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive"
                  disabled={!anySet || clear.isPending} onClick={() => clear.mutate()}>
            Remove all keys
          </Button>
          <Button size="sm" disabled={!Object.keys(pending).length || save.isPending}
                  onClick={() => save.mutate(pending)}>
            {save.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
