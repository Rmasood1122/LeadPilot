"use client";

/** F06 Quickstart — website + one-line offer → review-only first drafts while
 *  the full research pipeline runs.
 *
 *  REVIEW ONLY. A draft can be copied or discarded — there is no approve or
 *  send control, because there is no send path: outreach happens only through
 *  the verified strategy's sequence. The banner says so in plain words. */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Info, Trash2 } from "lucide-react";

import { ApiError } from "@/lib/api/client";
import {
  discardQuickstartDraft,
  getQuickstart,
  getQuickstartConfig,
  listQuickstarts,
  startQuickstart,
} from "@/lib/api/quickstart";
import {
  MAX_OFFER,
  STAGES,
  formatDuration,
  icpSummary,
  isInProgress,
  normalizeWebsite,
  offerError,
  stageIndex,
  visibleDrafts,
  type QuickstartDraft,
  type QuickstartRun,
} from "@/lib/quickstart";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : fallback;
}

export default function QuickstartPage() {
  const config = useQuery({ queryKey: ["quickstart-config"], queryFn: getQuickstartConfig });
  const enabled = config.data?.enabled === true;
  const runs = useQuery({
    queryKey: ["quickstart-runs"],
    queryFn: listQuickstarts,
    enabled,
  });
  const [selected, setSelected] = useState<string | null>(null);
  const current = selected ?? runs.data?.items[0]?.id ?? null;

  if (config.isLoading) return <p className="p-6 text-sm text-muted-foreground">Loading…</p>;
  if (!enabled) {
    return (
      <div className="mx-auto max-w-xl space-y-2 py-6">
        <h1 className="text-xl font-semibold">Quickstart</h1>
        <p className="text-sm text-muted-foreground">
          Quickstart is not enabled on this deployment. You can still{" "}
          <Link className="underline" href="/strategies/new">create a strategy</Link>.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 py-2">
      <div>
        <h1 className="text-xl font-semibold">Quickstart</h1>
        <p className="text-sm text-muted-foreground">
          Your website and one line about your offer. We find up to {config.data?.lead_target} verified
          leads and draft a first email to each, while the full research runs.
        </p>
      </div>
      <StartForm onStarted={(id) => setSelected(id)} />
      {runs.data && runs.data.items.length > 1 && (
        <div className="flex flex-wrap gap-2" aria-label="Earlier Quickstart runs">
          {runs.data.items.map((run) => (
            <Button key={run.id} size="sm" variant={run.id === current ? "default" : "ghost"}
                    onClick={() => setSelected(run.id)}>
              {new URL(run.website_url).hostname}
            </Button>
          ))}
        </div>
      )}
      {current && <RunView id={current} />}
    </div>
  );
}

function StartForm({ onStarted }: { onStarted: (id: string) => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [website, setWebsite] = useState("");
  const [offer, setOffer] = useState("");
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);

  const normalized = normalizeWebsite(website);
  const urlError = touched && !normalized ? "Enter your website, like example.com." : null;
  const offerMsg = touched ? offerError(offer) : null;

  const start = useMutation({
    mutationFn: () => startQuickstart({
      website_url: normalized ?? website, offer, ...(name.trim() ? { product_name: name.trim() } : {}),
    }),
    onSuccess: (run) => {
      qc.invalidateQueries({ queryKey: ["quickstart-runs"] });
      onStarted(run.id);
      toast("Quickstart started — the full research is running too", "success");
    },
    onError: (e) => toast(errorText(e, "Could not start Quickstart"), "error"),
  });

  return (
    <Card>
      <CardContent className="space-y-3 p-gutter">
        <form className="space-y-3" onSubmit={(e) => {
          e.preventDefault();
          setTouched(true);
          if (normalizeWebsite(website) && !offerError(offer)) start.mutate();
        }}>
          <div>
            <Label htmlFor="qs-website">Website</Label>
            <Input id="qs-website" inputMode="url" autoComplete="url" placeholder="example.com"
                   value={website} onChange={(e) => setWebsite(e.target.value)}
                   aria-invalid={!!urlError} aria-describedby="qs-website-error" />
            {urlError && <p id="qs-website-error" className="text-xs text-destructive">{urlError}</p>}
          </div>
          <div>
            <Label htmlFor="qs-offer">Your offer, in one line</Label>
            <Input id="qs-offer" maxLength={MAX_OFFER}
                   placeholder="Automated NFPA inspection reports for fire contractors"
                   value={offer} onChange={(e) => setOffer(e.target.value)}
                   aria-invalid={!!offerMsg} aria-describedby="qs-offer-error" />
            {offerMsg && <p id="qs-offer-error" className="text-xs text-destructive">{offerMsg}</p>}
          </div>
          <div>
            <Label htmlFor="qs-name">Product name (optional)</Label>
            <Input id="qs-name" maxLength={200} value={name}
                   onChange={(e) => setName(e.target.value)} />
          </div>
          <Button type="submit" disabled={start.isPending}>
            {start.isPending ? "Starting…" : "Start Quickstart"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function RunView({ id }: { id: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["quickstart-run", id],
    queryFn: () => getQuickstart(id),
    refetchInterval: (query) => {
      const run = query.state.data as QuickstartRun | undefined;
      return run && !isInProgress(run.status) ? false : 10_000;
    },
  });
  const [showDiscarded, setShowDiscarded] = useState(false);

  return (
    <AsyncState isLoading={isLoading} error={error} empty={!data} emptyLabel="Run not found.">
      {data && (
        <div className="space-y-3">
          <div role="note" className="flex gap-2 rounded border border-border bg-muted p-3 text-sm">
            <Info size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <p>
              These drafts are <strong>for review only</strong> — nothing is sent from here.
              Outreach starts from the verified strategy once its research and verification
              finish, and every message is rewritten then.{" "}
              <Link className="underline" href={`/strategies/detail?id=${data.strategy_id}`}>
                Follow the full research
              </Link>.
            </p>
          </div>
          <Progress run={data} />
          {visibleDrafts(data.drafts, showDiscarded).length > 0 && (
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold">
                Drafts ({visibleDrafts(data.drafts).length})
              </h2>
              <Button size="sm" variant="ghost" onClick={() => setShowDiscarded((v) => !v)}>
                {showDiscarded ? "Hide discarded" : "Show discarded"}
              </Button>
            </div>
          )}
          <ul className="space-y-3">
            {visibleDrafts(data.drafts, showDiscarded).map((draft) => (
              <DraftCard key={draft.id} draft={draft} runId={data.id} />
            ))}
          </ul>
        </div>
      )}
    </AsyncState>
  );
}

function Progress({ run }: { run: QuickstartRun }) {
  const at = stageIndex(run.status);
  return (
    <Card>
      <CardHeader className="gap-1">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-sm">{run.website_url}</CardTitle>
          {run.superseded
            ? <Badge tone="success">Verified strategy ready</Badge>
            : run.status === "failed"
              ? <Badge tone="destructive">Stopped</Badge>
              : <Badge tone={run.status === "ready" ? "success" : "accent"}>
                  {run.status === "ready" ? "Ready" : "Running"}
                </Badge>}
        </div>
        <p className="text-xs text-muted-foreground">{run.offer}</p>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <ol className="space-y-1" aria-label="Quickstart progress">
          {STAGES.map((stage, i) => {
            const done = run.status === "ready" || (at >= 0 && i < at);
            const active = i === at && run.status !== "ready";
            return (
              <li key={stage.status} className="flex items-center gap-2"
                  aria-current={active ? "step" : undefined}>
                <span aria-hidden="true">{done ? <Check size={14} /> : active ? "…" : "·"}</span>
                <span className={done || active ? "" : "text-muted-foreground"}>
                  {stage.label}{done ? " — done" : active ? " — in progress" : ""}
                </span>
              </li>
            );
          })}
        </ol>
        {run.error && <p className="text-destructive">{run.error}</p>}
        {run.batch?.error && <p className="text-destructive">Lead sourcing: {run.batch.error}</p>}
        {run.icp && <p className="text-muted-foreground">Looking for: {icpSummary(run.icp)}</p>}
        <p className="text-xs text-muted-foreground">
          First draft after {formatDuration(run.seconds_to_first_draft)}
          {run.budget_usd !== null && ` · AI spend $${run.spent_usd.toFixed(2)} of $${run.budget_usd.toFixed(2)}`}
        </p>
      </CardContent>
    </Card>
  );
}

function DraftCard({ draft, runId }: { draft: QuickstartDraft; runId: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(t);
  }, [copied]);

  const discard = useMutation({
    mutationFn: () => discardQuickstartDraft(draft.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quickstart-run", runId] }),
    onError: (e) => toast(errorText(e, "Could not discard"), "error"),
  });

  async function copy() {
    try {
      await navigator.clipboard.writeText(`${draft.subject}\n\n${draft.body}`);
      setCopied(true);
    } catch {
      toast("Copy is not available here", "error");
    }
  }

  const who = [draft.lead?.full_name, draft.lead?.title, draft.lead?.company]
    .filter(Boolean).join(" · ");
  return (
    <li>
      <Card className={draft.status === "discarded" ? "opacity-60" : undefined}>
        <CardHeader className="gap-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-sm">{who || draft.lead?.email || "Lead"}</CardTitle>
            <Badge tone="warning">{draft.label}</Badge>
          </div>
          {draft.lead?.email && <p className="text-xs text-muted-foreground">{draft.lead.email}</p>}
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p className="font-medium">{draft.subject}</p>
          <p className="whitespace-pre-wrap">{draft.body}</p>
          {draft.claims_changed > 0 && (
            <p className="text-xs text-muted-foreground">
              {draft.claims_changed} unsupported claim{draft.claims_changed === 1 ? " was" : "s were"} removed.
            </p>
          )}
          <div className="flex gap-2">
            <Button size="sm" variant="ghost" onClick={copy}>
              <Copy size={14} aria-hidden="true" /> {copied ? "Copied" : "Copy"}
            </Button>
            {draft.status !== "discarded" && (
              <Button size="sm" variant="ghost" disabled={discard.isPending}
                      onClick={() => discard.mutate()}>
                <Trash2 size={14} aria-hidden="true" /> Discard
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </li>
  );
}
