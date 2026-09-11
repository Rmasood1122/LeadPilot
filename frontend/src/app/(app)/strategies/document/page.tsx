"use client";

/** The strategy document, plus what Feature Group 1 knows about it:
 *
 *   Document       the document itself, with an UNCERTAIN ZONE badge on every
 *                  section where Claude and GPT-4o meaningfully disagreed.
 *                  Each badge opens both positions side by side, and the full
 *                  raw outputs of both models on demand.
 *   Versions       the original and every mutation proposal: apply, dismiss,
 *                  or propose one now.
 *   Market signals the live news / Apollo signals the research was given.
 *
 * `tab` lives in the URL so the "strategy mutated" notification can open the
 * Versions tab directly. Printing (Export to PDF) prints the document only. */

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, RefreshCw, Sparkles } from "lucide-react";

import { getStrategyDocument } from "@/lib/api/strategies";
import {
  applyVersion,
  dismissVersion,
  getIntelligence,
  getModelOutputs,
  getVersion,
  mutateStrategy,
  refreshMarketSignals,
  type StrategyVersionSummary,
  type UncertainZone,
} from "@/lib/api/intelligence";
import { splitSections, zonesByPhase } from "@/lib/strategy-sections";
import { Markdown } from "@/components/strategy/Markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Modal } from "@/components/ui/dialog";
import { AsyncState } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";

const TABS = ["document", "versions", "signals"] as const;
type Tab = (typeof TABS)[number];

export default function StrategyDocumentPage() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const id = searchParams.get("id") ?? "";
  const tabParam = searchParams.get("tab");
  const tab: Tab = (TABS as readonly string[]).includes(tabParam ?? "") ? (tabParam as Tab) : "document";

  const doc = useQuery({
    queryKey: ["strategy-document", id],
    queryFn: () => getStrategyDocument(id),
    enabled: !!id,
  });
  const intel = useQuery({
    queryKey: ["strategy-intelligence", id],
    queryFn: () => getIntelligence(id),
    enabled: !!id,
  });
  const [compare, setCompare] = useState<UncertainZone | null>(null);

  const zones = intel.data?.zones ?? [];
  const proposed = (intel.data?.versions ?? []).filter((v) => v.status === "proposed").length;

  return (
    <div className="print-doc mx-auto max-w-3xl space-y-6">
      <div className="no-print flex flex-wrap items-center justify-between gap-2">
        <ConsensusBadge status={intel.data?.consensus_status ?? null} zoneCount={zones.length} />
        <Button variant="outline" onClick={() => window.print()}>Export to PDF</Button>
      </div>

      <Tabs value={tab} onValueChange={(t) => router.replace(`/strategies/document?id=${id}&tab=${t}`)}>
        <TabsList className="no-print">
          <TabsTrigger value="document">Document</TabsTrigger>
          <TabsTrigger value="versions">
            Versions{proposed > 0 && <Badge tone="warning" className="ml-1">{proposed}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="signals">Market signals</TabsTrigger>
        </TabsList>

        <TabsContent value="document">
          <AsyncState isLoading={doc.isLoading} error={doc.error}
                      empty={!doc.data?.strategy_document && !doc.data?.gtm_document}
                      emptyLabel="Documents appear once the pipeline finishes.">
            {zones.length > 0 && (
              <div role="note" className="no-print mb-6 flex gap-3 rounded-lg border border-warning bg-card p-4 text-sm">
                <AlertTriangle className="shrink-0 text-warning" size={18} aria-hidden="true" />
                <p>
                  <span className="font-medium">
                    {zones.length} uncertain zone{zones.length === 1 ? "" : "s"}.
                  </span>{" "}
                  Two independent models (Claude and GPT-4o) wrote each section and disagreed on
                  the points flagged below. The document follows Claude; check the flagged points
                  before acting on them.
                </p>
              </div>
            )}
            {doc.data?.strategy_document && (
              <DocumentWithZones
                title="Execution strategy"
                markdown={doc.data.strategy_document}
                zones={zones.filter((z) => z.pipeline === "strategy")}
                onCompare={setCompare}
              />
            )}
            {doc.data?.gtm_document && (
              <div className="mt-8">
                <DocumentWithZones
                  title="Go-to-market plan"
                  markdown={doc.data.gtm_document}
                  zones={zones.filter((z) => z.pipeline === "gtm")}
                  onCompare={setCompare}
                />
              </div>
            )}
          </AsyncState>
        </TabsContent>

        <TabsContent value="versions" className="no-print">
          <VersionsPanel strategyId={id} versions={intel.data?.versions ?? []}
                         loading={intel.isLoading} />
        </TabsContent>

        <TabsContent value="signals" className="no-print">
          <SignalsPanel strategyId={id} intel={intel.data ?? null} loading={intel.isLoading} />
        </TabsContent>
      </Tabs>

      {compare && <CompareDialog strategyId={id} zone={compare} onClose={() => setCompare(null)} />}
    </div>
  );
}

function ConsensusBadge({ status, zoneCount }: { status: string | null; zoneCount: number }) {
  if (!status) return <span />;
  return (
    <Badge tone={status === "complete" ? (zoneCount ? "warning" : "success") : "default"}>
      {status === "complete"
        ? zoneCount ? `Cross-checked · ${zoneCount} disagreement${zoneCount === 1 ? "" : "s"}` : "Cross-checked · models agree"
        : "Partly cross-checked (second model unavailable on some sections)"}
    </Badge>
  );
}

function DocumentWithZones({
  title,
  markdown,
  zones,
  onCompare,
}: {
  title: string;
  markdown: string;
  zones: UncertainZone[];
  onCompare: (zone: UncertainZone) => void;
}) {
  const { preamble, sections } = splitSections(markdown);
  const byPhase = zonesByPhase(zones);
  return (
    <article aria-label={title}>
      <h1 className="mb-4 text-2xl font-semibold">{title}</h1>
      {preamble && !/^#\s/.test(preamble) && <Markdown source={preamble} />}
      {sections.map((section, i) => {
        const sectionZones = section.phase !== null ? byPhase.get(section.phase) ?? [] : [];
        return (
          <section key={i} className="relative">
            {sectionZones.length > 0 && (
              <div className="no-print mt-4 flex flex-wrap gap-2">
                {sectionZones.map((zone) => (
                  <button
                    key={zone.id}
                    type="button"
                    onClick={() => onCompare(zone)}
                    className="inline-flex items-center gap-1 rounded border border-warning px-2 py-0.5 text-xs font-medium hover:bg-muted"
                    title="Claude and GPT-4o disagreed here — click to compare"
                  >
                    <AlertTriangle size={12} className="text-warning" aria-hidden="true" />
                    Uncertain{zone.severity === "high" ? " (high)" : ""}: {zone.topic}
                  </button>
                ))}
              </div>
            )}
            <Markdown source={section.body} />
          </section>
        );
      })}
    </article>
  );
}

function CompareDialog({ strategyId, zone, onClose }: {
  strategyId: string;
  zone: UncertainZone;
  onClose: () => void;
}) {
  const [showFull, setShowFull] = useState(false);
  const outputs = useQuery({
    queryKey: ["model-outputs", strategyId, zone.pipeline, zone.step_no],
    queryFn: () => getModelOutputs(strategyId, zone.step_no, zone.pipeline),
    enabled: showFull,
  });
  return (
    <Modal open onClose={onClose} title={`Uncertain zone: ${zone.topic}`} className="max-w-3xl">
      <div className="space-y-4 text-sm">
        <p className="text-muted-foreground">
          Section: {zone.section_title} · severity {zone.severity}
          {zone.similarity !== null && ` · text similarity ${Math.round(zone.similarity * 100)}%`}
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          <Card>
            <CardHeader><CardTitle className="text-sm">Claude (used in the document)</CardTitle></CardHeader>
            <CardContent><p className="whitespace-pre-wrap">{zone.claude_position || "—"}</p></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm">GPT-4o</CardTitle></CardHeader>
            <CardContent><p className="whitespace-pre-wrap">{zone.gpt_position || "—"}</p></CardContent>
          </Card>
        </div>
        {!showFull ? (
          <Button size="sm" variant="outline" onClick={() => setShowFull(true)}>
            Show both models&apos; full answers for this section
          </Button>
        ) : (
          <AsyncState isLoading={outputs.isLoading} error={outputs.error}>
            <div className="grid gap-3 md:grid-cols-2">
              {(outputs.data ?? []).map((o) => (
                <div key={o.provider} className="max-h-96 overflow-y-auto rounded border border-border p-3">
                  <p className="mb-2 text-xs font-medium text-muted-foreground">
                    {o.provider === "anthropic" ? "Claude" : "GPT-4o"} · {o.model}
                  </p>
                  {o.output ? <Markdown source={o.output} /> : <p className="text-destructive">{o.error}</p>}
                </div>
              ))}
            </div>
          </AsyncState>
        )}
      </div>
    </Modal>
  );
}

const VERSION_TONE: Record<string, "success" | "warning" | "default" | "destructive"> = {
  applied: "success",
  proposed: "warning",
  superseded: "default",
  dismissed: "default",
};

function VersionsPanel({ strategyId, versions, loading }: {
  strategyId: string;
  versions: StrategyVersionSummary[];
  loading: boolean;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [viewing, setViewing] = useState<string | null>(null);
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["strategy-intelligence", strategyId] });
    qc.invalidateQueries({ queryKey: ["strategy-document", strategyId] });
  };
  const onError = (e: unknown) => toast((e as Error).message, "error");
  const propose = useMutation({
    mutationFn: () => mutateStrategy(strategyId),
    onSuccess: () => { refresh(); toast("Mutation proposed — review it below", "success"); },
    onError,
  });
  const apply = useMutation({
    mutationFn: (versionId: string) => applyVersion(strategyId, versionId),
    onSuccess: () => { refresh(); toast("Version applied — new outreach uses it", "success"); },
    onError,
  });
  const dismiss = useMutation({
    mutationFn: (versionId: string) => dismissVersion(strategyId, versionId),
    onSuccess: () => { refresh(); toast("Proposal dismissed", "success"); },
    onError,
  });
  const version = useQuery({
    queryKey: ["strategy-version", strategyId, viewing],
    queryFn: () => getVersion(strategyId, viewing as string),
    enabled: !!viewing,
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <p className="text-muted-foreground">
          A campaign with 7 days of sends and no replies gets a proposed mutation automatically.
          Nothing changes until you apply it.
        </p>
        <Button size="sm" variant="outline" disabled={propose.isPending} onClick={() => propose.mutate()}>
          <Sparkles size={14} aria-hidden="true" /> {propose.isPending ? "Thinking…" : "Propose a mutation now"}
        </Button>
      </div>
      <AsyncState isLoading={loading} error={null} empty={versions.length === 0}
                  emptyLabel="No versions yet. The original is recorded the first time the strategy mutates.">
        <ol className="space-y-3">
          {versions.map((v) => {
            const c = v.changes_json;
            return (
              <li key={v.id} className="space-y-2 rounded-lg border border-border bg-card p-4 text-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">Version {v.version_no}</span>
                  <Badge tone={VERSION_TONE[v.status] ?? "default"}>{v.status}</Badge>
                  <span className="text-xs text-muted-foreground">
                    {v.trigger.replace(/_/g, " ")} · {new Date(v.created_at).toLocaleString()}
                  </span>
                </div>
                {c ? (
                  <>
                    <p><span className="font-medium">Diagnosis.</span> {c.diagnosis}</p>
                    <p><span className="font-medium">New angle.</span> {c.messaging_angle.proposed}</p>
                    {c.channel.recommended && (
                      <p><span className="font-medium">Channel.</span> {c.channel.recommended} — {c.channel.rationale}</p>
                    )}
                    {c.icp_refinement.changes.length > 0 && (
                      <ul className="list-disc pl-5">
                        {c.icp_refinement.changes.map((change, i) => <li key={i}>{change}</li>)}
                      </ul>
                    )}
                  </>
                ) : (
                  <p className="text-muted-foreground">{v.change_summary}</p>
                )}
                <div className="flex flex-wrap gap-2 pt-1">
                  <Button size="sm" variant="ghost" onClick={() => setViewing(v.id)}>View document</Button>
                  {v.status !== "applied" && (
                    <Button size="sm" disabled={apply.isPending} onClick={() => apply.mutate(v.id)}>Apply</Button>
                  )}
                  {v.status === "proposed" && (
                    <Button size="sm" variant="ghost" disabled={dismiss.isPending}
                            onClick={() => dismiss.mutate(v.id)}>Dismiss</Button>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </AsyncState>
      {viewing && (
        <Modal open onClose={() => setViewing(null)} title="Version document" className="max-w-3xl">
          <AsyncState isLoading={version.isLoading} error={version.error}>
            {version.data && <Markdown source={version.data.document} />}
          </AsyncState>
        </Modal>
      )}
    </div>
  );
}

const SIGNAL_LABEL: Record<string, string> = {
  funding: "Funding", hiring: "Hiring / leadership", launch: "Launches & partnerships", news: "Other news",
};

function SignalsPanel({ strategyId, intel, loading }: {
  strategyId: string;
  intel: { market_signals: import("@/lib/api/intelligence").MarketSignals | null;
           market_signals_fetched_at: string | null } | null;
  loading: boolean;
}) {
  const toast = useToast();
  const refresh = useMutation({
    mutationFn: () => refreshMarketSignals(strategyId),
    onSuccess: () => toast("Refreshing — new signals are used by the next research run", "info"),
    onError: (e) => toast((e as Error).message, "error"),
  });
  const payload = intel?.market_signals;
  const signals = payload?.signals ?? [];
  return (
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground">
          {payload
            ? `Fetched ${new Date(payload.fetched_at).toLocaleString()} for: ${payload.queries.join(", ") || "—"}. These were given to the research as headlines to check, not facts.`
            : "No market signals were fetched for this strategy."}
        </p>
        <Button size="sm" variant="outline" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
          <RefreshCw size={14} aria-hidden="true" /> Refresh
        </Button>
      </div>
      <AsyncState isLoading={loading} error={null} empty={signals.length === 0}
                  emptyLabel="No signals found.">
        {(["funding", "hiring", "launch", "news"] as const).map((kind) => {
          const group = signals.filter((s) => s.type === kind);
          if (!group.length) return null;
          return (
            <Card key={kind}>
              <CardHeader><CardTitle className="text-sm">{SIGNAL_LABEL[kind]}</CardTitle></CardHeader>
              <CardContent>
                <ul className="space-y-1.5">
                  {group.map((s, i) => (
                    <li key={i} className="flex items-start justify-between gap-2">
                      <span>
                        {s.url ? (
                          <a href={s.url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                            {s.title}
                          </a>
                        ) : s.title}
                        {s.company && s.source === "google_news" && (
                          <span className="text-muted-foreground"> — {s.company}</span>
                        )}
                      </span>
                      <span className="shrink-0 text-xs text-muted-foreground">
                        {s.published_at ? new Date(s.published_at).toLocaleDateString() : s.source}
                        {s.url && <ExternalLink size={10} className="ml-1 inline" aria-hidden="true" />}
                      </span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          );
        })}
      </AsyncState>
      {payload?.errors?.length ? (
        <p className="text-xs text-muted-foreground">
          Some sources were unavailable: {payload.errors.join("; ")}
        </p>
      ) : null}
    </div>
  );
}
