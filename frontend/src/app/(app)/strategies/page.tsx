"use client";

import Link from "next/link";
import { useStrategies } from "@/lib/api/hooks";
import { AsyncState } from "@/components/ui/skeleton";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export default function StrategiesPage() {
  const { data, isLoading, error } = useStrategies();
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Strategies</h1>
        <Link href="/strategies/new" className="inline-flex h-10 items-center justify-center gap-2 rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90">New strategy</Link>
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
