"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useStrategies } from "@/lib/api/hooks";
import { getQuickstartConfig } from "@/lib/api/quickstart";
import { AsyncState } from "@/components/ui/skeleton";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function StrategiesPage() {
  const { data, isLoading, error } = useStrategies();
  // F06: the Quickstart entry shows only where the deployment has it on.
  const quickstart = useQuery({ queryKey: ["quickstart-config"], queryFn: getQuickstartConfig,
                                staleTime: 300_000 });
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Strategies</h1>
        <div className="flex gap-2">
          {quickstart.data?.enabled && (
            <Link href="/quickstart" className="inline-flex h-10 items-center justify-center gap-2 rounded border border-border px-4 py-2 text-sm font-medium hover:bg-muted">Quickstart</Link>
          )}
          <Link href="/strategies/new" className="inline-flex h-10 items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">New strategy</Link>
        </div>
      </div>
      <AsyncState isLoading={isLoading} error={error} empty={!data?.length}
                  emptyLabel="No strategies yet — start with a product or skill.">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {data?.map((s) => (
            <Link key={s.id} href={`/strategies/detail?id=${s.id}`}>
              <Card className="h-full transition-shadow hover:shadow-md">
                <CardContent className="space-y-2 p-gutter">
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium">
                      {(s as unknown as { product_name?: string }).product_name ?? "Strategy"}
                    </span>
                    <Badge tone={statusTone(s.status)}>{s.status}</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {s.flow_type === "with_clients"
                      ? "72-step pipeline (past clients)"
                      : "144-step pipeline (strategy + GTM)"}
                  </p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </AsyncState>
    </div>
  );
}
