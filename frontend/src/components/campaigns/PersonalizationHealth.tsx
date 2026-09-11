"use client";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";

interface PersonalizationHealthProps {
  strategyId: string;
}

const INDICATOR_STYLES: Record<string, { bg: string; text: string; dot: string }> = {
  green:  { bg: "bg-green-50 border-green-200",  text: "text-green-800", dot: "bg-green-500" },
  yellow: { bg: "bg-amber-50 border-amber-200",   text: "text-amber-800", dot: "bg-amber-500" },
  grey:   { bg: "bg-muted border-border",          text: "text-muted-foreground", dot: "bg-muted-foreground" },
};

export function PersonalizationHealth({ strategyId }: PersonalizationHealthProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["personalization-stats", strategyId],
    queryFn: () =>
      apiClient.get(`/strategies/${strategyId}/personalization-stats`),
  });

  if (isLoading) return null;
  if (!data || data.sample_size < 10) return null;

  const style = INDICATOR_STYLES[data.health_indicator ?? "grey"] ?? INDICATOR_STYLES.grey;

  return (
    <div className={`rounded-md border p-3 flex items-center gap-3 ${style.bg}`}>
      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${style.dot}`} />
      <div>
        <p className={`text-xs font-medium ${style.text}`}>{data.health_label}</p>
        {data.correlation != null && (
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Personalization ↔ reply correlation: {(data.correlation * 100).toFixed(0)}%
            {" "}(avg score: {((data.avg_score ?? 0) * 100).toFixed(0)}%)
          </p>
        )}
      </div>
    </div>
  );
}
