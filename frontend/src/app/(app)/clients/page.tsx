"use client";

/** Part 1 Feature 11 — the agency's client list: `/clients`.
 *
 *  An agency's screen, not a client's. Every row is one book of business with
 *  its own numbers, its own reserved sending domains and its own invoice —
 *  and the campaigns filed under NO client are shown at the top rather than
 *  hidden, because work that belongs to nobody is exactly the work that stops
 *  being invoiced.
 *
 *  A client with no reserved domain is labelled as such. An empty pool is
 *  permissive by design (nothing changes for an account that never sets one
 *  up), so the UI has to say so rather than let someone assume an isolation
 *  they do not have. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Building2, Plus, X } from "lucide-react";

import {
  addClientDomain,
  createClient,
  getClientBilling,
  listClients,
  removeClientDomain,
} from "@/lib/api/clients";
import {
  billingMismatch,
  clientSubtitle,
  money,
  poolWarning,
  rate,
  sortClients,
  statusTone,
  unassignedWarning,
  type ClientReport,
  type ClientWorkspace,
} from "@/lib/clients";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export default function ClientsPage() {
  const toast = useToast();
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [retainer, setRetainer] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["clients"],
    queryFn: () => listClients(),
  });
  const create = useMutation({
    mutationFn: () => createClient({
      name,
      monthly_fee_cents: retainer ? Math.round(Number(retainer) * 100) : undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      setAdding(false);
      setName("");
      setRetainer("");
      toast("Client added", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const clients = sortClients(data?.clients ?? []);
  const unassigned = unassignedWarning(data);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="flex items-center gap-2 text-xl font-semibold">
          <Building2 size={20} aria-hidden="true" /> Clients
        </h1>
        <Button onClick={() => setAdding((open) => !open)}>
          <Plus size={16} aria-hidden="true" /> Add a client
        </Button>
      </div>

      {adding && (
        <Card>
          <CardContent className="flex flex-wrap items-end gap-2 p-gutter">
            <div>
              <Label htmlFor="client-name">Client name</Label>
              <Input id="client-name" value={name}
                     onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="client-retainer">Monthly retainer</Label>
              <Input id="client-retainer" type="number" min="0" value={retainer}
                     onChange={(e) => setRetainer(e.target.value)} className="w-32" />
            </div>
            <Button disabled={!name.trim() || create.isPending}
                    onClick={() => create.mutate()}>
              {create.isPending ? "Adding…" : "Add"}
            </Button>
          </CardContent>
        </Card>
      )}

      {unassigned && (
        <p className="flex items-start gap-2 text-sm font-medium">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          {unassigned}
        </p>
      )}

      <AsyncState isLoading={isLoading} error={error} empty={!clients.length}
                  emptyLabel="No clients yet. Campaigns you run for yourself need no client.">
        <ul className="space-y-3">
          {clients.map((client) => <ClientRow key={client.id} client={client} />)}
        </ul>
      </AsyncState>

      {data && <p className="text-xs text-muted-foreground">{data.note}</p>}
    </div>
  );
}

function ClientRow({ client }: { client: ClientWorkspace & ClientReport }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [domain, setDomain] = useState("");
  const [showBilling, setShowBilling] = useState(false);

  const billing = useQuery({
    queryKey: ["client-billing", client.id],
    queryFn: () => getClientBilling(client.id),
    enabled: showBilling,
  });
  const done = (message: string) => {
    qc.invalidateQueries({ queryKey: ["clients"] });
    toast(message, "success");
  };
  const addDomain = useMutation({
    mutationFn: () => addClientDomain(client.id, domain),
    onSuccess: () => { setDomain(""); done("Domain reserved"); },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const dropDomain = useMutation({
    mutationFn: (value: string) => removeClientDomain(client.id, value),
    onSuccess: () => done("Domain released"),
    onError: (e) => toast((e as Error).message, "error"),
  });

  const warning = poolWarning(client);
  const mismatch = billingMismatch(billing.data);

  return (
    <li>
      <Card>
        <CardHeader className="gap-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-sm">{client.name}</CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(client.status)}>{client.status}</Badge>
              <Badge tone="default">{money(client.monthly_fee_cents, client.currency)}/mo</Badge>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">{clientSubtitle(client)}</p>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap gap-6">
            <Metric label="Sent" value={String(client.sent)} />
            <Metric label="Reply rate" value={rate(client.reply_rate)} />
            <Metric label="Meetings" value={String(client.meetings)} />
            <Metric label="Revenue"
                    value={money(client.revenue_cents, client.currency)} />
          </div>

          {warning && (
            <p className="flex items-start gap-2 text-xs text-muted-foreground">
              <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
              {warning}
            </p>
          )}

          <div className="flex flex-wrap items-end gap-2">
            {client.sending_domains.map((value) => (
              <Badge key={value} tone="default">
                {value}
                <button type="button" className="ml-1" aria-label={`Release ${value}`}
                        onClick={() => dropDomain.mutate(value)}>
                  <X size={10} aria-hidden="true" />
                </button>
              </Badge>
            ))}
            <div>
              <Label htmlFor={`domain-${client.id}`}>Reserve a sending domain</Label>
              <Input id={`domain-${client.id}`} value={domain} placeholder="outreach.example"
                     onChange={(e) => setDomain(e.target.value)} className="w-56" />
            </div>
            <Button size="sm" variant="outline"
                    disabled={!domain.trim() || addDomain.isPending}
                    onClick={() => addDomain.mutate()}>
              Reserve
            </Button>
          </div>

          <Button size="sm" variant="ghost" onClick={() => setShowBilling((o) => !o)}>
            {showBilling ? "Hide" : "Show"} this month&apos;s invoice
          </Button>

          {showBilling && (
            <AsyncState isLoading={billing.isLoading} error={billing.error}>
              {billing.data && (
                <div className="space-y-1">
                  <ul className="space-y-0.5 text-sm">
                    {billing.data.lines.map((line) => (
                      <li key={line.label} className="flex justify-between gap-4">
                        <span className="text-muted-foreground">{line.label}</span>
                        <span className="tabular-nums">
                          {money(line.amount_cents, billing.data!.currency)}
                        </span>
                      </li>
                    ))}
                    <li className="flex justify-between gap-4 border-t border-border pt-1 font-medium">
                      <span>Total from {billing.data.period_start}</span>
                      <span className="tabular-nums">
                        {money(billing.data.total_cents, billing.data.currency)}
                      </span>
                    </li>
                  </ul>
                  {mismatch && (
                    <p className="text-xs text-[rgb(var(--destructive))]">{mismatch}</p>
                  )}
                </div>
              )}
            </AsyncState>
          )}
        </CardContent>
      </Card>
    </li>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}
