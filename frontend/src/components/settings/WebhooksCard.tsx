"use client";

/** Feature Group 4: outbound webhooks (Zapier, Make, your own endpoint) and
 *  the personal API keys those tools authenticate with. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Trash2 } from "lucide-react";
import {
  createApiKey, deleteWebhook, listApiKeys, listWebhookDeliveries, listWebhookEvents,
  listWebhooks, registerWebhook, revokeApiKey, testWebhook,
} from "@/lib/api/ecosystem";
import { AsyncState } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { Modal } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";

function useCopy() {
  const toast = useToast();
  return async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied", "success");
    } catch {
      toast("Copy failed — select the text and copy it", "error");
    }
  };
}

/** A secret shown exactly once. */
function OneTimeSecret({ label, value, onDone }: { label: string; value: string; onDone: () => void }) {
  const copy = useCopy();
  return (
    <div className="space-y-2 rounded border border-warning bg-card p-3 text-sm" role="status">
      <p className="font-medium">{label}</p>
      <p className="text-xs text-muted-foreground">Copy it now — it will not be shown again.</p>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 break-all rounded bg-muted px-2 py-1 font-mono text-xs">{value}</code>
        <Button size="sm" variant="outline" onClick={() => copy(value)} aria-label="Copy">
          <Copy className="h-3.5 w-3.5" aria-hidden />
        </Button>
      </div>
      <Button size="sm" variant="outline" onClick={onDone}>Done</Button>
    </div>
  );
}

export function WebhooksCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);
  const targets = useQuery({ queryKey: ["webhooks"], queryFn: listWebhooks });
  const deliveries = useQuery({ queryKey: ["webhook-deliveries"], queryFn: listWebhookDeliveries });
  const fail = (e: unknown) => toast((e as Error).message, "error");

  const test = useMutation({
    mutationFn: testWebhook,
    onSuccess: (r) => {
      toast(`Sample ${r.event} queued`, "info");
      qc.invalidateQueries({ queryKey: ["webhook-deliveries"] });
    },
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: deleteWebhook,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["webhooks"] }),
    onError: fail,
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-sm">Webhooks (Zapier, Make)</CardTitle>
          <p className="text-xs text-muted-foreground">
            Signed POSTs for meeting booked, reply received, leads sourced, campaign paused and more.
          </p>
        </div>
        <Button size="sm" onClick={() => setOpen(true)}>Add webhook</Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {secret && (
          <OneTimeSecret label="Signing secret" value={secret} onDone={() => setSecret(null)} />
        )}
        <AsyncState isLoading={targets.isLoading} error={targets.error}
                    empty={!targets.data || targets.data.length === 0}
                    emptyLabel="No webhooks yet.">
          <ul className="divide-y divide-border text-sm">
            {targets.data?.map((t) => (
              <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <p className="truncate font-mono text-xs">{t.url}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {t.events.join(", ")} · {t.source}
                    {!t.active && ` · disabled${t.disabled_reason ? `: ${t.disabled_reason}` : ""}`}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" disabled={!t.active || test.isPending}
                          onClick={() => test.mutate(t.id)}>
                    Send test
                  </Button>
                  <button type="button" aria-label={`Delete webhook ${t.url}`}
                          className="rounded p-1 text-muted-foreground hover:text-[rgb(var(--destructive))]"
                          onClick={() => remove.mutate(t.id)}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </AsyncState>
        {(deliveries.data?.length ?? 0) > 0 && (
          <details>
            <summary className="cursor-pointer text-xs text-muted-foreground">Recent deliveries</summary>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[480px] text-xs" aria-label="Recent webhook deliveries">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="py-1 font-medium">Event</th>
                    <th className="font-medium">Status</th>
                    <th className="font-medium">Attempts</th>
                    <th className="font-medium">Last response</th>
                    <th className="font-medium">When</th>
                  </tr>
                </thead>
                <tbody>
                  {deliveries.data?.map((d) => (
                    <tr key={d.id} className="border-b border-border/50">
                      <td className="py-1">{d.event}</td>
                      <td>{d.status}</td>
                      <td className="tabular-nums">{d.attempts}</td>
                      <td>{d.last_status_code ?? d.last_error ?? "—"}</td>
                      <td>{d.created_at ? new Date(d.created_at).toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        )}
        <p className="text-[11px] text-muted-foreground">
          Verify <code>X-LeadPilot-Signature: t=…,v1=…</code> — HMAC-SHA256 of
          &quot;&lt;t&gt;.&lt;body&gt;&quot; with the signing secret. Answer 410 to unsubscribe.
        </p>
      </CardContent>
      <WebhookDialog open={open} onClose={() => setOpen(false)}
                     onCreated={(s) => { setSecret(s); setOpen(false); }} />
    </Card>
  );
}

function WebhookDialog({ open, onClose, onCreated }: {
  open: boolean;
  onClose: () => void;
  onCreated: (secret: string) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const events = useQuery({ queryKey: ["webhook-events"], queryFn: listWebhookEvents, enabled: open });
  const ordered = [...(events.data ?? [])].sort((a, b) => Number(b.zapier) - Number(a.zapier));

  const save = useMutation({
    mutationFn: () => registerWebhook({ url, events: picked, description: description || undefined }),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ["webhooks"] });
      setUrl(""); setDescription(""); setPicked([]);
      onCreated(t.secret ?? "");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const toggle = (name: string) =>
    setPicked((p) => (p.includes(name) ? p.filter((x) => x !== name) : [...p, name]));

  return (
    <Modal open={open} onClose={onClose} title="Add webhook">
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <div className="space-y-1">
          <Label htmlFor="wh-url">HTTPS URL</Label>
          <Input id="wh-url" type="url" required placeholder="https://hooks.zapier.com/hooks/catch/…"
                 value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">Events</legend>
          {ordered.map((ev) => (
            <label key={ev.event} className="flex items-start gap-2 text-sm">
              <input type="checkbox" className="mt-1" checked={picked.includes(ev.event)}
                     onChange={() => toggle(ev.event)} />
              <span>
                <span className="font-mono text-xs">{ev.event}</span>
                <span className="block text-xs text-muted-foreground">{ev.description}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <div className="space-y-1">
          <Label htmlFor="wh-desc">Description (optional)</Label>
          <Input id="wh-desc" maxLength={500} value={description}
                 onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={!url || picked.length === 0 || save.isPending}>Add</Button>
        </div>
      </form>
    </Modal>
  );
}

export function ApiKeysCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("Zapier");
  const [created, setCreated] = useState<string | null>(null);
  const { data, isLoading, error } = useQuery({ queryKey: ["api-keys"], queryFn: listApiKeys });
  const fail = (e: unknown) => toast((e as Error).message, "error");

  const create = useMutation({
    mutationFn: () => createApiKey(name),
    onSuccess: (k) => { setCreated(k.key ?? null); qc.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: fail,
  });
  const revoke = useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-keys"] }),
    onError: fail,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">API keys</CardTitle>
        <p className="text-xs text-muted-foreground">
          For Zapier, Make and scripts: <code>Authorization: Bearer lpk_…</code>. A key acts as
          you (never on admin routes); revoke it the moment it is not needed.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        {created && <OneTimeSecret label="New API key" value={created} onDone={() => setCreated(null)} />}
        <form className="flex flex-wrap items-end gap-2"
              onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <div className="space-y-1">
            <Label htmlFor="key-name">Name</Label>
            <Input id="key-name" maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <Button type="submit" size="sm" disabled={!name.trim() || create.isPending}>Create key</Button>
        </form>
        <AsyncState isLoading={isLoading} error={error} empty={!data || data.length === 0}
                    emptyLabel="No API keys.">
          <ul className="divide-y divide-border text-sm">
            {data?.map((k) => (
              <li key={k.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div>
                  <p className="font-medium">{k.name} <span className="font-mono text-xs text-muted-foreground">{k.prefix}…</span></p>
                  <p className="text-[11px] text-muted-foreground">
                    {k.revoked ? "Revoked" : `Last used ${k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "never"}`}
                  </p>
                </div>
                {!k.revoked && (
                  <Button size="sm" variant="outline" onClick={() => revoke.mutate(k.id)}>Revoke</Button>
                )}
              </li>
            ))}
          </ul>
        </AsyncState>
      </CardContent>
    </Card>
  );
}
