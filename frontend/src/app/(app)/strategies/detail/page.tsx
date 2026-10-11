"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useStrategy } from "@/lib/api/hooks";
import { DeleteStrategyDialog } from "@/components/strategy/DeleteStrategyDialog";
import { ResumeStrategyButton } from "@/components/strategy/ResumeStrategyButton";
import { ReverifyStrategyButton } from "@/components/strategy/ReverifyStrategyButton";
import { OverridePassesPanel } from "@/components/strategy/OverridePassesPanel";
import { OutreachPanel } from "@/components/strategy/OutreachPanel";
import { PipelineHealthCard } from "@/components/strategy/PipelineHealthCard";
import { AsyncState } from "@/components/ui/skeleton";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { PhaseProgress, PipelineProgress } from "@/lib/api/types";
import { verificationSummary } from "@/lib/strategyDetail";

function Phase({ phase }: { phase: PhaseProgress }) {
  const complete = phase.total > 0 && phase.done >= phase.total;
  return (
    <li className="flex items-center justify-between gap-3 py-1.5 text-sm">
      <span>{phase.phase}. {phase.title}</span>
      <span className="flex shrink-0 items-center gap-2">
        <span className="text-xs tabular-nums text-muted-foreground">
          {phase.done}/{phase.total}
        </span>
        <span className="h-2 w-24 overflow-hidden rounded bg-muted" role="progressbar"
              aria-valuenow={phase.done} aria-valuemax={phase.total} aria-label={phase.title}>
          <span
            className={complete ? "block h-full bg-success" : "block h-full bg-primary"}
            style={{ width: `${(phase.done / Math.max(phase.total, 1)) * 100}%` }}
          />
        </span>
      </span>
    </li>
  );
}

function Pipeline({ pipeline }: { pipeline: PipelineProgress }) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="text-sm">
          {pipeline.pipeline === "gtm" ? "GTM pipeline" : "Strategy pipeline"}
        </CardTitle>
        <span className="text-xs tabular-nums text-muted-foreground">
          {pipeline.done}/{pipeline.total} steps
        </span>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-border">
          {pipeline.phases.map((phase) => (
            <Phase key={phase.phase} phase={phase} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export default function StrategyDetailPage() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id") ?? "";
  const router = useRouter();
  const queryClient = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const { data, isLoading, error } = useStrategy(id, !deleted);

  function onDeleted() {
    setDeleted(true);
    setDeleteOpen(false);
    router.replace("/strategies");
    queryClient.removeQueries({ queryKey: ["strategy", id] });
  }

  return (
    <div className="space-y-4">
      <AsyncState isLoading={isLoading} error={error}>
        {data && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h1 className="text-xl font-semibold">Strategy</h1>
              <div className="flex items-center gap-2">
                <Badge tone={statusTone(data.status)}>{data.status}</Badge>
                <ResumeStrategyButton strategy={data} />
                <ReverifyStrategyButton strategy={data} />
                {(data.strategy_document_ready || data.gtm_document_ready) && (
                  <Button variant="outline" size="sm">
                    <Link href={`/strategies/document?id=${id}`}>View documents</Link>
                  </Button>
                )}
                <Button variant="outline" size="sm" className="gap-1 text-destructive"
                        onClick={() => setDeleteOpen(true)}>
                  <Trash2 size={14} aria-hidden="true" />
                  Delete
                </Button>
              </div>
            </div>
            <DeleteStrategyDialog
              strategyId={id}
              open={deleteOpen}
              onClose={() => setDeleteOpen(false)}
              onDeleted={onDeleted}
            />

            {data.status === "needs_human_review" && (
              <div role="alert"
                   className="rounded border border-warning bg-card p-4 text-sm">
                <p className="font-medium">Needs your review</p>
                <p className="text-muted-foreground">
                  A verification pass kept failing after the maximum fix
                  attempts. See the failing pass below for the reason, adjust
                  inputs, and re-run. If only a few failed and you have checked
                  them yourself, you can pass them manually.
                </p>
                <div className="mt-3">
                  <OverridePassesPanel strategyId={id} status={data.status}
                                       log={data.verification} />
                </div>
              </div>
            )}
            {(data.status === "verifying" || data.status === "budget_exhausted") && (
              <OverridePassesPanel strategyId={id} status={data.status}
                                   log={data.verification} />
            )}
            <OutreachPanel strategy={data} />
            {(data.status === "verified" || data.status === "executing") && (
              <PipelineHealthCard strategyId={id} />
            )}
            {data.error && (
              <div role="alert" className="rounded border border-destructive p-4 text-sm">
                {data.error}
              </div>
            )}

            <section aria-label="Pipeline progress" className="space-y-2">
              {data.progress.map((pipeline) => (
                <Pipeline key={pipeline.pipeline} pipeline={pipeline} />
              ))}
              <p className="text-xs text-muted-foreground">
                The outputs of individual research steps are not shown here; they
                are compiled into the strategy and GTM documents.
              </p>
            </section>

            <section aria-label="Verification loop">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">
                    10x verification loop
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {data.verification.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Runs after research completes.
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {verificationSummary(data.verification).map((pass) => (
                        <li key={pass.pass_no}
                            className="flex flex-wrap items-center justify-between gap-2 text-sm">
                          <span>
                            #{pass.pass_no} {pass.name}
                            {pass.note?.kind === "manual" && (
                              <span className="block text-xs text-muted-foreground">
                                passed manually by {pass.note.text}
                              </span>
                            )}
                            {pass.note?.kind === "fix" && (
                              <span className="block text-xs text-muted-foreground">
                                fix applied: {pass.note.text}
                              </span>
                            )}
                            {pass.note?.kind === "failure" && (
                              <span className="block text-xs text-muted-foreground">
                                why it failed: {pass.note.text}
                              </span>
                            )}
                          </span>
                          <Badge tone={pass.result === "PASS" ? "success" : "destructive"}>
                            {pass.manual ? "PASS (manual)" : pass.result}
                            {pass.attempts > 1 ? ` x${pass.attempts}` : ""}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
            </section>
          </>
        )}
      </AsyncState>
    </div>
  );
}