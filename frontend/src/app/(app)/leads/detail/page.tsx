"use client";

/** The lead detail page: `/leads/detail?id=<lead>&tab=<tab>`.
 *
 * ROUTE SHAPE: a query parameter, not `/leads/[id]`, for the same reason as
 * /strategies/detail and /meetings/detail -- next.config.js sets
 * `output: 'export'` (Capacitor bundles the static export), so a dynamic
 * segment cannot serve an id that did not exist at build time.
 *
 * `tab` is in the URL so push notifications can open a specific tab (the
 * meeting prep brief deep-links to `&tab=prep`) and so the back button
 * returns to the tab the user was on.
 *
 * The kanban drawer and the CRM grid panel stay the quick views; this page is
 * where the per-lead features that need room live. Later feature groups add
 * their tabs to TABS below. */

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ClipboardCheck, RefreshCw } from "lucide-react";

import { rescoreLead } from "@/lib/api/intelligence";
import { getLead } from "@/lib/api/leads";
import type { LeadOut } from "@/lib/api/types";
import { factorRows } from "@/lib/lead-score";
import { ScoreBadge } from "@/components/leads/ScoreBadge";
import { useToast } from "@/components/ui/toast";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AsyncState } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LogOutcomeDialog } from "@/components/leads/LogOutcomeDialog";
import { MeetingPrepPanel } from "@/components/leads/MeetingPrepPanel";
import { OutcomeHistory } from "@/components/leads/OutcomeHistory";
import { PersonalizationPanel } from "@/components/leads/PersonalizationPanel";
import { LeadCalls } from "@/components/calls/CallHistory";

const TABS = [
  { value: "overview", label: "Overview" },
  { value: "personalization", label: "Personalization" },
  { value: "calls", label: "Calls" },
  { value: "prep", label: "Meeting Prep" },
  { value: "outcomes", label: "Outcomes" },
] as const;
type Tab = (typeof TABS)[number]["value"];

function isTab(value: string | null): value is Tab {
  return TABS.some((t) => t.value === value);
}

export default function LeadDetailPage() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("id");
  const tabParam = params.get("tab");
  const tab: Tab = isTab(tabParam) ? tabParam : "overview";
  const [logOpen, setLogOpen] = useState(false);

  const query = useQuery({
    queryKey: ["lead", id],
    queryFn: () => getLead(id as string),
    enabled: !!id,
  });
  const lead = query.data;

  if (!id) {
    return (
      <p className="text-sm text-muted-foreground">
        No lead selected. Open one from the{" "}
        <Link href="/pipeline" className="underline underline-offset-2">Pipeline</Link> or the{" "}
        <Link href="/crm/table" className="underline underline-offset-2">CRM</Link>.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <Link
        href="/pipeline"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft size={12} aria-hidden="true" /> Pipeline
      </Link>

      <AsyncState isLoading={query.isLoading} error={query.error}>
        {lead && (
          <>
            <header className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h1 className="truncate text-xl font-semibold">
                  {lead.full_name ?? lead.email ?? "Lead"}
                </h1>
                <p className="text-sm text-muted-foreground">
                  {[lead.title, lead.company].filter(Boolean).join(" · ") || "—"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <ScoreBadge score={lead.ai_booking_likelihood} reason={lead.ai_score_reason} />
                <Badge tone={statusTone(lead.status)}>{lead.status.replace(/_/g, " ")}</Badge>
                <Button onClick={() => setLogOpen(true)}>
                  <ClipboardCheck size={16} aria-hidden="true" /> Log Meeting Outcome
                </Button>
              </div>
            </header>

            <Tabs
              value={tab}
              onValueChange={(next) => router.replace(`/leads/detail?id=${id}&tab=${next}`)}
            >
              <TabsList aria-label="Lead sections">
                {TABS.map((t) => (
                  <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>
                ))}
              </TabsList>
              <TabsContent value="overview"><LeadOverview lead={lead} /></TabsContent>
              <TabsContent value="personalization">
                <PersonalizationPanel leadId={lead.id} score={lead.ai_booking_likelihood} />
              </TabsContent>
              <TabsContent value="calls"><LeadCalls lead={lead} /></TabsContent>
              <TabsContent value="prep"><MeetingPrepPanel leadId={lead.id} /></TabsContent>
              <TabsContent value="outcomes"><OutcomeHistory leadId={lead.id} /></TabsContent>
            </Tabs>

            <LogOutcomeDialog lead={lead} open={logOpen} onClose={() => setLogOpen(false)} />
          </>
        )}
      </AsyncState>
    </div>
  );
}

/** Feature Group 1: the AI booking likelihood and the factors behind it.
 *  The factors are shown, not just the number, because a score nobody can
 *  explain is a score nobody should prioritise their day by. */
function LeadScoreCard({ lead }: { lead: LeadOut }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const rescore = useMutation({
    mutationFn: () => rescoreLead(lead.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["lead", lead.id] });
      toast("Score updated", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const rows = factorRows(lead.ai_score_factors);

  return (
    <Card className="lg:col-span-2">
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle>AI booking likelihood</CardTitle>
        <div className="flex items-center gap-2">
          <ScoreBadge score={lead.ai_booking_likelihood} reason={lead.ai_score_reason} />
          <Button size="sm" variant="ghost" disabled={rescore.isPending}
                  onClick={() => rescore.mutate()}>
            <RefreshCw size={14} aria-hidden="true" /> {rescore.isPending ? "Scoring…" : "Rescore"}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {lead.ai_score_reason && <p>{lead.ai_score_reason}</p>}
        {rows.length > 0 ? (
          <ul className="grid gap-2 sm:grid-cols-2">
            {rows.map((row) => (
              <li key={row.key}>
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{row.label}</span>
                  <span className="tabular-nums">{row.percent}%</span>
                </div>
                <div className="mt-1 h-1.5 rounded bg-muted" aria-hidden="true">
                  <div className="h-1.5 rounded bg-[rgb(var(--primary))]"
                       style={{ width: `${row.percent}%` }} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">
            Not scored yet. Leads are scored when a sourcing batch finishes; Rescore scores this one now.
          </p>
        )}
        {lead.ai_score_factors && (
          <p className="text-xs text-muted-foreground">
            Baseline from data: {lead.ai_score_factors.heuristic}/100.{" "}
            {lead.ai_score_factors.method === "model"
              ? "Adjusted by AI (at most ±20 points) from the lead's profile."
              : "The AI adjustment was unavailable, so the data baseline is shown."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function LeadOverview({ lead }: { lead: LeadOut }) {
  const enrichment = Object.entries(lead.enrichment_json ?? {}).filter(
    ([, v]) => typeof v === "string" || typeof v === "number",
  );
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <LeadScoreCard lead={lead} />
      <Card>
        <CardHeader><CardTitle>Contact</CardTitle></CardHeader>
        <CardContent>
          <dl className="grid grid-cols-[7rem_1fr] gap-x-3 gap-y-1.5 text-sm">
            <dt className="text-muted-foreground">Title</dt><dd>{lead.title ?? "—"}</dd>
            <dt className="text-muted-foreground">Company</dt><dd>{lead.company ?? "—"}</dd>
            <dt className="text-muted-foreground">Email</dt><dd className="break-all">{lead.email ?? "—"}</dd>
            <dt className="text-muted-foreground">Phone</dt><dd>{lead.phone ?? "—"}</dd>
            <dt className="text-muted-foreground">Source</dt><dd>{(lead as LeadOut & { source?: string }).source ?? "—"}</dd>
          </dl>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>Enrichment</CardTitle></CardHeader>
        <CardContent>
          {enrichment.length ? (
            <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-1.5 text-sm">
              {enrichment.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="break-all">{String(v)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">No flat enrichment fields on record.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
