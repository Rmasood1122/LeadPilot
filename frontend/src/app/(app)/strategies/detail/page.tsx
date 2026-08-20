"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useStrategy } from "@/lib/api/hooks";
import { AsyncState } from "@/components/ui/skeleton";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Markdown } from "@/components/strategy/Markdown";
import type { PhaseProgress } from "@/lib/api/types";

const PHASE_NAMES: Record<string, string[]> = {
  strategy: [
    "Product decomposition", "ICP definition", "Market sizing",
    "Competitor analysis", "Channel analysis", "Messaging & offer",
    "Objections & proof", "Execution plan",
  ],
  gtm: [
    "Positioning", "Pricing", "Launch sequencing", "Channel budget",
    "Content plan", "Partnerships", "Sales motion", "Funnel metrics",
  ],
};

function Phase({ phase }: { phase: PhaseProgress }) {
  const [open, setOpen] = useState(false);
  // A pipeline that errors before progress data populates sends entries
  // with no phase/done/total - render a neutral label rather than
  // "undefined. Phase undefined".
  const numbered = Number.isFinite(phase.phase);
  const name = numbered
    ? PHASE_NAMES[phase.pipeline]?.[phase.phase - 1] ?? `Phase ${phase.phase}`
    : "Phase pending";
  const done = Number.isFinite(phase.done) ? phase.done : 0;
  const total = Number.isFinite(phase.total) ? phase.total : 0;
  const complete = total > 0 && done >= total;
  return (
    <Card>
      <button
        className="w-full text-left"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-sm">
            {phase.pipeline === "gtm" ? "GTM - " : ""}
            {numbered ? `${phase.phase}. ` : ""}{name}
          </CardTitle>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">
              {done}/{total}
            </span>
            <div className="h-2 w-24 overflow-hidden rounded bg-muted" role="progressbar"
                 aria-valuenow={done} aria-valuemax={total} aria-label={name}>
              <div
                className={complete ? "h-full bg-success" : "h-full bg-primary"}
                style={{ width: `${(done / Math.max(total, 1)) * 100}%` }}
              />
            </div>
          </div>
        </CardHeader>
      </button>
      {open && (
        <CardContent className="space-y-3">
          {(phase.steps ?? []).length === 0 && (
            <p className="text-sm text-muted-foreground">
              Step outputs appear here as they complete.
            </p>
          )}
          {(phase.steps ?? []).map((step) => (
            <details key={step.step_id} className="rounded border border-border p-2">
              <summary className="cursor-pointer text-sm font-medium">
                {step.step_id} - {step.name}
              </summary>
              <div className="mt-2">
                <Markdown source={step.output} />
              </div>
            </details>
          ))}
        </CardContent>
      )}
    </Card>
  );
}

export default function StrategyDetailPage() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id") ?? "";
  const { data, isLoading, error } = useStrategy(id);

  return (
    <div className="space-y-4">
      <AsyncState isLoading={isLoading} error={error}>
        {data && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h1 className="text-xl font-semibold">Strategy</h1>
              <div className="flex items-center gap-2">
                <Badge tone={statusTone(data.status)}>{data.status}</Badge>
                {(data.strategy_document_ready || data.gtm_document_ready) && (
                  <Button variant="outline" size="sm">
                    <Link href={`/strategies/document?id=${id}`}>View documents</Link>
                  </Button>
                )}
              </div>
            </div>

            {data.status === "needs_human_review" && (
              <div role="alert"
                   className="rounded border border-warning bg-card p-4 text-sm">
                <p className="font-medium">Needs your review</p>
                <p className="text-muted-foreground">
                  A verification pass kept failing after the maximum fix
                  attempts. See the failing pass below for the reason, adjust
                  inputs, and re-run.
                </p>
              </div>
            )}
            {data.error && (
              <div role="alert" className="rounded border border-destructive p-4 text-sm">
                {data.error}
              </div>
            )}

            <section aria-label="Pipeline progress" className="space-y-2">
              {data.progress.map((phase) => (
                <Phase key={`${phase.pipeline}-${phase.phase}`} phase={phase} />
              ))}
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
                      {data.verification.map((pass) => (
                        <li key={pass.pass_no}
                            className="flex flex-wrap items-center justify-between gap-2 text-sm">
                          <span>
                            #{pass.pass_no} {pass.name}
                            {pass.fix && (
                              <span className="block text-xs text-muted-foreground">
                                fix applied: {pass.fix}
                              </span>
                            )}
                          </span>
                          <Badge tone={pass.result === "PASS" ? "success" : "destructive"}>
                            {pass.result}
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