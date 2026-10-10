"use client";

/** F07 — Spend Guard: this month's spend against the account's own cap, the
 *  cap setting, 50/80/100% alerts, verified results vs the cost of every
 *  attempt, a forecast preview for sourcing leads, and forecast-vs-actual for
 *  recent runs.
 *
 *  Behind `spend_guard_enabled` (default off): a 409 renders one quiet line,
 *  not an error. */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import {
  getSpendUsage,
  previewEnrichmentForecast,
  setSpendCap,
  type ForecastPreview,
} from "@/lib/api/spendGuard";
import { listStrategies } from "@/lib/api/strategies";
import {
  accuracySummary,
  accuracyVerdict,
  alertBanner,
  barWidth,
  capTone,
  creditsLabel,
  formatUsd,
  isDisabledError,
  parseCapInput,
  thresholdReached,
  THRESHOLDS,
} from "@/lib/spendGuard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { StatTile } from "@/components/crm/dashboard/primitives";
import { cn } from "@/lib/utils";

const KIND_LABEL: Record<string, string> = {
  strategy_run: "Strategy run",
  enrichment_run: "Lead sourcing",
  quickstart: "Quickstart",
};

export function SpendGuardPanel() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["spend-guard-usage"],
    queryFn: getSpendUsage,
    retry: (count, err) => !isDisabledError(err) && count < 2,
  });

  const [capText, setCapText] = useState("");
  const [emailAlerts, setEmailAlerts] = useState(true);
  const [capError, setCapError] = useState<string | null>(null);
  useEffect(() => {
    if (!data) return;
    setCapText(data.cap.monthly_cap_usd === null ? "" : String(data.cap.monthly_cap_usd));
    setEmailAlerts(data.cap.email_alerts);
  }, [data]);

  const saveCap = useMutation({
    mutationFn: ({ value, alerts }: { value: number | null; alerts: boolean }) =>
      setSpendCap(value, alerts),
    onSuccess: (usage) => {
      queryClient.setQueryData(["spend-guard-usage"], usage);
      toast(usage.cap.monthly_cap_usd === null ? "Monthly cap removed" : "Monthly cap saved", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  if (isDisabledError(error)) {
    return (
      <Card aria-label="Spend Guard">
        <CardContent className="p-gutter text-sm text-muted-foreground">
          Spend Guard is off. An administrator can turn it on in Admin › System Settings
          (<code>spend_guard_enabled</code>).
        </CardContent>
      </Card>
    );
  }

  const percent = data?.spend.percent_of_cap ?? null;
  const reached = thresholdReached(percent);
  const banner = alertBanner(reached);
  const tone = capTone(percent);

  const submitCap = () => {
    const parsed = parseCapInput(capText);
    if (!parsed.ok) {
      setCapError(parsed.error);
      return;
    }
    setCapError(null);
    saveCap.mutate({ value: parsed.value, alerts: emailAlerts });
  };

  return (
    <AsyncState isLoading={isLoading} error={error}>
      {data && (
        <div className="space-y-6">
          {banner && (
            <div role="alert"
                 className={cn("flex items-start gap-2 rounded border bg-card p-3 text-sm",
                               reached === 100 ? "border-[rgb(var(--destructive))]" : "border-warning")}>
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-[rgb(var(--warning))]" aria-hidden />
              {banner}
            </div>
          )}

          <Card aria-label="This month">
            <CardHeader>
              <CardTitle className="text-sm">This month ({data.period.label}, UTC)</CardTitle>
              <p className="text-xs text-muted-foreground">
                AI spend plus priced data credits. The monthly cap is in addition to your plan&apos;s
                daily AI limit ({formatUsd(data.daily.limit_usd)} per day, {formatUsd(data.daily.spent_today_usd)} used
                today) — it can only lower what may be spent, never raise it.
              </p>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <StatTile label="Total" value={formatUsd(data.spend.total_usd)}
                          tone={tone === "default" ? "default" : tone}
                          sub={data.cap.monthly_cap_usd === null ? "no monthly cap"
                            : `of ${formatUsd(data.cap.monthly_cap_usd)} (${percent}%)`} />
                <StatTile label="AI" value={formatUsd(data.spend.ai_usd)} sub="metered model spend" />
                <StatTile label="Data credits" value={formatUsd(data.spend.data_usd)}
                          sub={creditsLabel(data.spend.data_credits)} />
                <StatTile label="Left this month"
                          value={data.spend.remaining_usd === null ? "—"
                            : formatUsd(Math.max(data.spend.remaining_usd, 0))} />
              </div>

              {data.cap.monthly_cap_usd !== null && (
                <div aria-label="Cap used" className="space-y-1">
                  <div className="relative h-2 w-full overflow-hidden rounded bg-muted">
                    <div className={cn("h-full rounded",
                                       tone === "danger" ? "bg-[rgb(var(--destructive))]"
                                         : tone === "warning" ? "bg-[rgb(var(--warning))]"
                                           : "bg-[rgb(var(--primary))]")}
                         style={{ width: `${barWidth(percent)}%` }} />
                    {THRESHOLDS.slice(0, 2).map((t) => (
                      <span key={t} aria-hidden className="absolute top-0 h-full w-px bg-border"
                            style={{ left: `${t}%` }} />
                    ))}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    Alerts at 50%, 80% and 100%, once each per month.
                  </p>
                </div>
              )}

              {data.pricing.providers.some((p) => !p.priced) && (
                <p className="text-[11px] text-muted-foreground">
                  Not priced yet:{" "}
                  {data.pricing.providers.filter((p) => !p.priced).map((p) => p.provider).join(", ")}
                  {" "}— their credits are counted, but not in dollars, until an administrator sets a
                  price per credit.
                </p>
              )}
            </CardContent>
          </Card>

          <Card aria-label="Monthly cap">
            <CardHeader><CardTitle className="text-sm">Monthly spend cap</CardTitle></CardHeader>
            <CardContent>
              <form className="flex flex-wrap items-end gap-3"
                    onSubmit={(e) => { e.preventDefault(); submitCap(); }}>
                <div className="space-y-1">
                  <Label htmlFor="spend-cap">Cap (USD per month)</Label>
                  <Input id="spend-cap" inputMode="decimal" placeholder="No cap" className="w-40"
                         value={capText} onChange={(e) => setCapText(e.target.value)} />
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={emailAlerts}
                         onChange={(e) => setEmailAlerts(e.target.checked)} />
                  Email me at 50%, 80% and 100%
                </label>
                <Button type="submit" size="sm" disabled={saveCap.isPending}>Save</Button>
              </form>
              {capError && <p className="mt-2 text-xs text-[rgb(var(--destructive))]">{capError}</p>}
              <p className="mt-2 text-[11px] text-muted-foreground">
                Leave empty for no monthly cap. Only an owner or a manager can change it. Runs whose
                forecast does not fit in what is left are refused before they start; a running one stops
                before its next paid call. Scheduled sends are never stopped.
              </p>
              {data.alerts.length > 0 && (
                <ul className="mt-3 space-y-1 text-xs" aria-label="Alerts this month">
                  {data.alerts.map((a) => (
                    <li key={a.threshold}>
                      {a.threshold}% reached{a.fired_at ? ` on ${a.fired_at.slice(0, 10)}` : ""} —
                      {" "}{formatUsd(a.spent_usd)} of {formatUsd(a.cap_usd)}
                      {a.email_status === "failed" ? " (email failed)" : ""}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card aria-label="Verified results and attempt cost">
            <CardHeader><CardTitle className="text-sm">Verified results vs. attempt cost</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <StatTile label="Verified results" value={data.billable.verified_results}
                          sub={`${data.billable.finalized_batches} finished batches`} />
                <StatTile label="Data attempts" value={data.billable.data_attempts}
                          sub={`${data.billable.paid_data_attempts} paid`} />
                <StatTile label="Attempt cost" value={formatUsd(data.billable.internal_data_usd)}
                          sub={creditsLabel(data.billable.data_credits)} />
                <StatTile label="Cost / verified result"
                          value={formatUsd(data.billable.cost_per_verified_result_usd)} />
              </div>
              <p className="text-[11px] text-muted-foreground">{data.billable.note}</p>
            </CardContent>
          </Card>

          <ForecastPreviewCard />

          <Card aria-label="Recent forecasts">
            <CardHeader>
              <CardTitle className="text-sm">Recent forecasts</CardTitle>
              <p className="text-xs text-muted-foreground">{accuracySummary(data.accuracy)}</p>
            </CardHeader>
            <CardContent>
              {data.forecasts.length === 0 ? (
                <p className="text-sm text-muted-foreground">No runs forecast yet this month.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[620px] text-sm" aria-label="Forecast vs actual">
                    <thead>
                      <tr className="border-b border-border text-left text-xs text-muted-foreground">
                        <th className="py-1.5 font-medium">When</th>
                        <th className="font-medium">Run</th>
                        <th className="text-right font-medium">Forecast</th>
                        <th className="text-right font-medium">Actual</th>
                        <th className="pl-3 font-medium">±25%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.forecasts.map((f) => {
                        const verdict = accuracyVerdict(f);
                        return (
                          <tr key={f.forecast_id} className="border-b border-border/50 tabular-nums">
                            <td className="py-1.5">{f.created_at?.slice(0, 16).replace("T", " ")}</td>
                            <td>{KIND_LABEL[f.kind] ?? f.kind}{f.decision === "refused" ? " (refused)" : ""}</td>
                            <td className="text-right">{formatUsd(f.forecast_usd)}</td>
                            <td className="text-right">{f.actual_usd === undefined ? "—" : formatUsd(f.actual_usd)}</td>
                            <td className={cn("pl-3 text-xs",
                                              verdict.tone === "warning" ? "text-[rgb(var(--warning))]"
                                                : "text-muted-foreground")}>
                              {verdict.text}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </AsyncState>
  );
}

function ForecastPreviewCard() {
  const toast = useToast();
  const { data: strategies } = useQuery({ queryKey: ["strategies"], queryFn: listStrategies });
  const [strategyId, setStrategyId] = useState("");
  const [leads, setLeads] = useState("50");
  const [preview, setPreview] = useState<ForecastPreview | null>(null);
  const run = useMutation({
    mutationFn: () => previewEnrichmentForecast(strategyId, Math.max(1, Number(leads) || 1)),
    onSuccess: setPreview,
    onError: (e) => toast((e as Error).message, "error"),
  });

  return (
    <Card aria-label="Forecast a lead-sourcing run">
      <CardHeader>
        <CardTitle className="text-sm">Forecast a lead-sourcing run</CardTitle>
        <p className="text-xs text-muted-foreground">
          What sourcing leads would cost before you start it. Nothing is spent or saved.
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <form className="flex flex-wrap items-end gap-3"
              onSubmit={(e) => { e.preventDefault(); if (strategyId) run.mutate(); }}>
          <div className="space-y-1">
            <Label htmlFor="forecast-strategy">Strategy</Label>
            <select id="forecast-strategy" value={strategyId} onChange={(e) => setStrategyId(e.target.value)}
                    className="rounded border border-border bg-card px-2 py-2 text-sm">
              <option value="">Choose…</option>
              {strategies?.map((s) => (
                <option key={s.id} value={s.id}>
                  {(s as unknown as { product_name?: string }).product_name ?? s.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="forecast-leads">Leads</Label>
            <Input id="forecast-leads" inputMode="numeric" className="w-24" value={leads}
                   onChange={(e) => setLeads(e.target.value)} />
          </div>
          <Button type="submit" size="sm" variant="outline" disabled={!strategyId || run.isPending}>
            Forecast
          </Button>
        </form>
        {preview && (
          <div className="space-y-1 text-sm">
            <p>
              <span className="font-medium">{formatUsd(preview.forecast.total_usd)}</span> expected for{" "}
              {preview.forecast.requested_leads} leads — AI {formatUsd(preview.forecast.ai.usd)}, data{" "}
              {formatUsd(preview.forecast.data.usd)} ({creditsLabel(preview.forecast.data.credits)}).
            </p>
            <p className={cn("text-xs", preview.would_allow ? "text-muted-foreground"
              : "text-[rgb(var(--destructive))]")}>
              {preview.would_allow
                ? (preview.remaining_usd === null ? "No monthly cap is set."
                  : `Fits: ${formatUsd(preview.remaining_usd)} left this month.`)
                : `Would be refused: only ${formatUsd(Math.max(preview.remaining_usd ?? 0, 0))} left this month.`}
            </p>
            <p className="text-[11px] text-muted-foreground">{preview.forecast.sends.note}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
