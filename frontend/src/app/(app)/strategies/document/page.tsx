"use client";

import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getStrategyDocument } from "@/lib/api/strategies";
import { AsyncState } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/strategy/Markdown";

export default function StrategyDocumentPage() {
  const searchParams = useSearchParams();
  const id = searchParams.get("id") ?? "";
  const { data, isLoading, error } = useQuery({
    queryKey: ["strategy-document", id],
    queryFn: () => getStrategyDocument(id),
  });

  return (
    <div className="print-doc mx-auto max-w-3xl space-y-6">
      <div className="no-print flex justify-end">
        <Button variant="outline" onClick={() => window.print()}>
          Export to PDF
        </Button>
      </div>
      <AsyncState isLoading={isLoading} error={error}
                  empty={!data?.strategy_document && !data?.gtm_document}
                  emptyLabel="Documents appear once the pipeline finishes.">
        {data?.strategy_document && (
          <article aria-label="Strategy document">
            <h1 className="mb-4 text-2xl font-semibold">Execution strategy</h1>
            <Markdown source={data.strategy_document} />
          </article>
        )}
        {data?.gtm_document && (
          <article aria-label="GTM document" className="mt-8">
            <h1 className="mb-4 text-2xl font-semibold">Go-to-market plan</h1>
            <Markdown source={data.gtm_document} />
          </article>
        )}
      </AsyncState>
    </div>
  );
}