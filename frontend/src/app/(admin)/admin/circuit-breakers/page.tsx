"use client";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api/admin";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

const STATE_VARIANTS: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  CLOSED: "secondary",
  OPEN: "destructive",
  HALF_OPEN: "outline",
};

export default function CircuitBreakersPage() {
  const qc = useQueryClient();

  const { data: breakers = [], isLoading } = useQuery({
    queryKey: ["admin", "circuit-breakers"],
    queryFn: () => adminApi.listCircuitBreakers(),
    refetchInterval: 15000, // auto-refresh every 15s
  });

  const resetMutation = useMutation({
    mutationFn: (provider: string) => adminApi.resetCircuitBreaker(provider),
    onSuccess: (_, provider) => {
      qc.invalidateQueries({ queryKey: ["admin", "circuit-breakers"] });
      toast.success(`Circuit for ${provider} reset to CLOSED`);
    },
    onError: () => toast.error("Reset failed"),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Circuit Breakers</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Auto-refreshes every 15 seconds. Reset a circuit manually after verifying the external service recovered.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading…</div>
      ) : breakers.length === 0 ? (
        <div className="rounded-md border p-8 text-center text-muted-foreground">
          No circuit breakers registered yet. They appear when external integrations are first used.
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {breakers.map((cb: any) => (
            <div
              key={cb.provider}
              className="rounded-lg border p-4 space-y-3 bg-card"
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold capitalize">{cb.provider}</span>
                <Badge variant={STATE_VARIANTS[cb.state] || "default"}>
                  {cb.state}
                </Badge>
              </div>
              <div className="text-sm space-y-1 text-muted-foreground">
                <div>Failures: <span className="text-foreground font-medium">{cb.failure_count}</span></div>
                <div>Total opens: <span className="text-foreground font-medium">{cb.total_opens}</span></div>
                {cb.last_failure_time && (
                  <div>
                    Last failure:{" "}
                    <span className="text-foreground">
                      {new Date(cb.last_failure_time * 1000).toLocaleTimeString()}
                    </span>
                  </div>
                )}
                {cb.next_retry_time && cb.state === "OPEN" && (
                  <div>
                    Retrying at:{" "}
                    <span className="text-foreground">
                      {new Date(cb.next_retry_time * 1000).toLocaleTimeString()}
                    </span>
                  </div>
                )}
              </div>
              {cb.state !== "CLOSED" && (
                <Button
                  size="sm"
                  variant="outline"
                  className="w-full"
                  disabled={resetMutation.isPending}
                  onClick={() => resetMutation.mutate(cb.provider)}
                >
                  Reset to CLOSED
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
