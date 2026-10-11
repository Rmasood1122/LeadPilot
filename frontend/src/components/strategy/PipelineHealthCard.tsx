"use client";

import { useQuery } from "@tanstack/react-query";
import { getPipelineHealth } from "@/lib/api/pipelineHealth";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const BAND_TONE: Record<string, "destructive" | "warning" | "success" | "accent"> = {
  critical: "destructive", low: "warning", moderate: "accent", strong: "success",
};

const PARTS: [keyof import("@/lib/api/pipelineHealth").PipelineHealth["components"], string][] = [
  ["reply_rate", "Reply rate"],
  ["completion", "Sequence completion"],
  ["freshness", "Lead freshness"],
  ["conversations", "Open conversations"],
];

/** Product defect #23: the Pipeline Health Score (GET /strategies/{id}/health)
 *  had no UI. Shown on the strategy page once outreach can exist. */
export function PipelineHealthCard({ strategyId }: { strategyId: string }) {
  const { data } = useQuery({
    queryKey: ["pipeline-health", strategyId],
    queryFn: () => getPipelineHealth(strategyId),
    staleTime: 60_000,
  });
  if (!data) return null;
  return (
    <section aria-label="Pipeline health">
      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle className="text-sm">Pipeline health</CardTitle>
          <Badge tone={BAND_TONE[data.band] ?? "accent"}>
            {data.score}/100 {data.band}
          </Badge>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p>{data.message}</p>
          <ul className="grid grid-cols-2 gap-1 text-xs text-muted-foreground sm:grid-cols-4">
            {PARTS.map(([key, label]) => (
              <li key={key}>{label}: {Math.round(data.components[key])}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </section>
  );
}
