"use client";
import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/lib/api/admin";
import { Badge } from "@/components/ui/badge";

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
    ok: "secondary",
    degraded: "outline",
    down: "destructive",
    error: "destructive",
    unknown: "outline",
  };
  return (
    <Badge variant={variants[status] ?? "default"} className="capitalize">
      {status}
    </Badge>
  );
}

export default function SystemHealthPage() {
  const { data: health, isLoading: healthLoading } = useQuery({
    queryKey: ["admin", "health"],
    queryFn: () => adminApi.getSystemHealth(),
    refetchInterval: 30000,
  });

  const { data: llHealth, isLoading: llLoading } = useQuery({
    queryKey: ["admin", "health", "learning-loop"],
    queryFn: () => adminApi.getLearningLoopHealth(),
    refetchInterval: 60000,
  });

  const { data: celeryStats } = useQuery({
    queryKey: ["admin", "celery-stats"],
    queryFn: () => adminApi.getCeleryStats(),
    refetchInterval: 30000,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">System Health</h1>

      {/* Core components */}
      <section className="space-y-3">
        <h2 className="font-semibold text-muted-foreground uppercase text-xs tracking-wider">
          Core Components
        </h2>
        {healthLoading ? (
          <div className="text-muted-foreground">Loading…</div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            {Object.entries(health?.components ?? {}).map(([name, comp]: [string, any]) => (
              <div key={name} className="rounded-lg border p-4 bg-card space-y-2">
                <div className="flex items-center justify-between">
                  <span className="capitalize font-medium">{name}</span>
                  <StatusBadge status={comp.status} />
                </div>
                {comp.last_beat_seconds_ago != null && (
                  <p className="text-xs text-muted-foreground">
                    Last heartbeat: {comp.last_beat_seconds_ago}s ago
                  </p>
                )}
                {comp.error && (
                  <p className="text-xs text-destructive">{comp.error}</p>
                )}
                {comp.reason && (
                  <p className="text-xs text-muted-foreground">{comp.reason}</p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Learning loop */}
      <section className="space-y-3">
        <h2 className="font-semibold text-muted-foreground uppercase text-xs tracking-wider">
          Learning Loop
        </h2>
        {llLoading ? (
          <div className="text-muted-foreground">Loading…</div>
        ) : (
          <div className="rounded-lg border p-4 bg-card space-y-2">
            <div className="flex items-center gap-3">
              <StatusBadge status={llHealth?.status ?? "unknown"} />
              <span className="text-sm">
                {llHealth?.last_run_at
                  ? `Last run ${llHealth.last_run_seconds_ago}s ago`
                  : "No aggregation run recorded yet"}
              </span>
            </div>
            {llHealth?.patterns_updated_last_run != null && (
              <p className="text-sm text-muted-foreground">
                Patterns updated last run: {llHealth.patterns_updated_last_run}
              </p>
            )}
            {llHealth?.last_run_duration_ms != null && (
              <p className="text-sm text-muted-foreground">
                Duration: {(llHealth.last_run_duration_ms / 1000).toFixed(1)}s
              </p>
            )}
            {llHealth?.last_error && (
              <p className="text-sm text-destructive">{llHealth.last_error}</p>
            )}
            {llHealth?.recommendation && (
              <p className="text-xs text-muted-foreground italic">{llHealth.recommendation}</p>
            )}
          </div>
        )}
      </section>

      {/* Celery queues */}
      <section className="space-y-3">
        <h2 className="font-semibold text-muted-foreground uppercase text-xs tracking-wider">
          Celery Workers & Queues
        </h2>
        <div className="rounded-lg border p-4 bg-card">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <p className="text-sm font-medium">Active Workers</p>
              <p className="text-2xl font-bold">{celeryStats?.active_workers ?? "—"}</p>
            </div>
            <div>
              <p className="text-sm font-medium">Active Tasks</p>
              <p className="text-2xl font-bold">{celeryStats?.active_tasks ?? "—"}</p>
            </div>
          </div>
          {celeryStats?.queues && (
            <div className="mt-4 space-y-1">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Queue Depths</p>
              {Object.entries(celeryStats.queues).map(([queue, info]: [string, any]) => (
                <div key={queue} className="flex items-center justify-between text-sm">
                  <span className="font-mono">{queue}</span>
                  <span className="font-medium">{info.depth}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
