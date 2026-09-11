"use client";

/** Feature Group 9: sending-domain health, blacklist status and the per-send
 *  compliance audit log. Every status has an icon AND a word — colour is
 *  never the only signal. */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";
import {
  DECISION_LABELS, getDeliverability, healthTone, listComplianceAudit, runDeliverabilityCheck,
  type DomainHealth,
} from "@/lib/api/trust";
import { AsyncState } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { Sparkline, StatTile } from "@/components/crm/dashboard/primitives";

function Check({ ok, label, note }: { ok: boolean | null; label: string; note?: string }) {
  const Icon = ok === null ? HelpCircle : ok ? CheckCircle2 : XCircle;
  const tone = ok === null ? "text-muted-foreground"
    : ok ? "text-[rgb(var(--success))]" : "text-[rgb(var(--destructive))]";
  return (
    <li className="flex items-start gap-2 text-sm">
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} aria-hidden />
      <span>
        <span className="font-medium">{label}</span>{" "}
        <span className="text-muted-foreground">
          {ok === null ? "unknown" : ok ? "OK" : "missing"}{note ? ` · ${note}` : ""}
        </span>
      </span>
    </li>
  );
}

function DomainPanel({ d, threshold }: { d: DomainHealth; threshold: number }) {
  const listed = d.blacklist?.listed_on ?? [];
  const details = d.health?.details;
  return (
    <div className="space-y-3 rounded border border-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-medium">{d.domain}</p>
          <p className="text-xs text-muted-foreground">{d.address}</p>
        </div>
        {d.health && (
          <p className="text-xs text-muted-foreground">
            Checked {new Date(d.health.checked_at).toLocaleString()} · {d.health.source}
          </p>
        )}
      </div>
      {listed.length > 0 && (
        <div role="alert" className="flex gap-2 rounded border border-[rgb(var(--destructive))] p-2 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[rgb(var(--destructive))]" aria-hidden />
          <span>
            Listed on <strong>{listed.join(", ")}</strong>. Campaigns were paused. Request delisting
            from each list, then resume the campaigns.
          </span>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
        <StatTile
          label="Health"
          value={d.health ? `${d.health.score}/100` : "—"}
          tone={healthTone(d.health?.score, threshold)}
          sub={d.health ? (d.health.score >= threshold ? "above threshold" : `below ${threshold}`) : "not checked yet"}
        />
        <div className="space-y-2">
          <ul className="space-y-1">
            <Check ok={details ? details.spf : null} label="SPF" />
            <Check ok={details ? details.dmarc : null} label="DMARC"
                   note={details?.dmarc_policy ? `p=${details.dmarc_policy}` : undefined} />
            <Check ok={details ? details.dkim : null} label="DKIM" note="Google selector" />
            <Check ok={d.blacklist ? listed.length === 0 : null} label="Blocklists"
                   note={d.blacklist?.unknown.length ? `${d.blacklist.unknown.length} could not be queried` : undefined} />
          </ul>
          {details?.bounce_rate != null && (
            <p className="text-xs text-muted-foreground">
              Bounce rate (30 days): {(details.bounce_rate * 100).toFixed(1)}%
            </p>
          )}
        </div>
      </div>
      {(details?.reasons.length ?? 0) > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground">
          {details?.reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}
      {d.history.length > 1 && (
        <Sparkline points={d.history.map((h) => h.score)} label={`Health score history for ${d.domain}`} />
      )}
    </div>
  );
}

export function DeliverabilityCard() {
  const qc = useQueryClient();
  const toast = useToast();
  const { data, isLoading, error } = useQuery({ queryKey: ["deliverability"], queryFn: getDeliverability });
  const run = useMutation({
    mutationFn: runDeliverabilityCheck,
    onSuccess: (d) => { qc.setQueryData(["deliverability"], d); toast("Checks complete", "success"); },
    onError: (e) => toast((e as Error).message, "error"),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="text-sm">Email health</CardTitle>
          <p className="text-xs text-muted-foreground">
            SPF, DKIM, DMARC, bounce rate and domain blocklists for each sending domain, checked daily
            {data && !data.monitoring_enabled ? " (daily monitoring is off on this deployment)" : ""}.
            A Mailreach key adds inbox-placement data.
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={() => run.mutate()} disabled={run.isPending}>
          {run.isPending ? "Checking…" : "Run check now"}
        </Button>
      </CardHeader>
      <CardContent>
        <AsyncState isLoading={isLoading} error={error} empty={!data || data.domains.length === 0}
                    emptyLabel="Connect a Gmail account on your own domain to monitor it (gmail.com and other shared domains are Google's reputation, not yours).">
          <div className="space-y-3">
            {data?.domains.map((d) => <DomainPanel key={d.domain} d={d} threshold={data.threshold} />)}
          </div>
        </AsyncState>
      </CardContent>
    </Card>
  );
}

export function ComplianceAuditCard() {
  const { data, isLoading, error } = useQuery({ queryKey: ["compliance-audit"], queryFn: () => listComplianceAudit(50) });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Compliance audit log</CardTitle>
        <p className="text-xs text-muted-foreground">
          Every send and every compliance block, with the recipient&apos;s region and the regime
          applied (CAN-SPAM, GDPR, CASL, PDPA…). A record of what was checked, not legal advice.
        </p>
      </CardHeader>
      <CardContent>
        <AsyncState isLoading={isLoading} error={error} empty={!data || data.length === 0}
                    emptyLabel="No sends recorded yet.">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm" aria-label="Compliance audit log">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-1.5 font-medium">When</th>
                  <th className="font-medium">Channel</th>
                  <th className="font-medium">Region</th>
                  <th className="font-medium">Regime</th>
                  <th className="font-medium">Decision</th>
                  <th className="font-medium">Legal basis</th>
                </tr>
              </thead>
              <tbody>
                {data?.map((r) => (
                  <tr key={r.id} className="border-b border-border/50">
                    <td className="py-1.5 tabular-nums">{r.ts ? new Date(r.ts).toLocaleString() : "—"}</td>
                    <td className="capitalize">{r.channel}</td>
                    <td className="uppercase">{r.region ?? "unknown"}</td>
                    <td>{r.regime ?? "—"}</td>
                    <td>{DECISION_LABELS[r.decision] ?? r.decision}</td>
                    <td className="max-w-[18rem] truncate text-xs text-muted-foreground"
                        title={String(r.checks?.legal_basis ?? "")}>
                      {String(r.checks?.legal_basis ?? "—")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AsyncState>
      </CardContent>
    </Card>
  );
}
