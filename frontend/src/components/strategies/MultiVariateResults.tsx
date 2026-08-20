"use client";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";

interface MultiVariateResultsProps {
  strategyId: string;
  metric?: string;
}

export function MultiVariateResults({
  strategyId,
  metric = "meeting_rate",
}: MultiVariateResultsProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["mv-results", strategyId, metric],
    queryFn: () =>
      apiClient
        .get(`/strategies/${strategyId}/mv-results?metric=${metric}`)
        .then((r: any) => r.data),
  });

  if (isLoading) return <div className="text-sm text-muted-foreground">Loading test results…</div>;

  if (!data || data.message) {
    return (
      <div className="text-sm text-muted-foreground">
        {data?.message ?? "Not enough data yet for multi-variant comparison."}
      </div>
    );
  }

  const sortedVariants: any[] = Object.values(data.per_variant_stats ?? {}).sort(
    (a: any, b: any) => a.rank - b.rank
  );

  return (
    <div className="space-y-4">
      {/* Winner banner */}
      {data.winner && (
        <div className="rounded-md bg-green-50 border border-green-200 p-3 text-sm text-green-800">
          🏆 <strong>{data.winner}</strong> is the winner. {data.recommendation}
        </div>
      )}

      {/* Ranked table */}
      <div className="space-y-2">
        {sortedVariants.map((v: any) => (
          <div
            key={v.variant}
            className={`rounded-lg border p-3 flex items-center justify-between ${
              v.variant === data.winner ? "border-green-300 bg-green-50/50" : ""
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground font-mono w-4">#{v.rank}</span>
              <span className="font-medium text-sm">{v.variant}</span>
              {data.harm_flags?.[v.variant] && (
                <Badge variant="destructive" className="text-[10px]">⚠ harm</Badge>
              )}
            </div>
            <div className="flex items-center gap-4 text-sm">
              <span>{(v.rate * 100).toFixed(1)}%</span>
              <span className="text-xs text-muted-foreground">n={v.sample_size}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Overall significance */}
      <div className="text-xs text-muted-foreground flex items-center gap-2">
        <span>
          Kruskal-Wallis p={data.overall_p_value?.toFixed(4)}{" "}
          {data.overall_significant ? "✓ significant" : "✗ not significant"}
        </span>
        {data.pairwise_results?.length > 0 && (
          <span>
            · {data.pairwise_results.filter((r: any) => r.significant).length} of{" "}
            {data.pairwise_results.length} pairs significant (Bonferroni corrected)
          </span>
        )}
      </div>

      {!data.winner && !data.overall_significant && (
        <p className="text-xs text-muted-foreground">
          {data.recommendation}
        </p>
      )}
    </div>
  );
}
