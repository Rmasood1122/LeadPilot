// app/(dashboard)/strategies/[id]/campaigns/page.tsx
// M5 campaigns page + M8-C4 PersonalizationHealth + MultiVariateResults additions.
"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";
import { CampaignSequenceView } from "@/components/campaigns/CampaignSequenceView";
import { LeadStatusBoard } from "@/components/campaigns/LeadStatusBoard";
import { PersonalizationHealth } from "@/components/campaigns/PersonalizationHealth";
import { MultiVariateResults } from "@/components/strategies/MultiVariateResults";

export default function CampaignsPage() {
  const { id: strategyId } = useParams() as { id: string };

  if (!strategyId) return null;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Campaign</h1>

      {/* Personalization health indicator (C4) */}
      <Suspense fallback={null}>
        <PersonalizationHealth strategyId={strategyId} />
      </Suspense>

      {/* Sequence view */}
      <CampaignSequenceView strategyId={strategyId} />

      {/* Lead status board */}
      <LeadStatusBoard strategyId={strategyId} />

      {/* A/B / Multi-variate results (C4) */}
      <section className="space-y-3">
        <h2 className="font-semibold">Variant Performance</h2>
        <Suspense fallback={<div className="text-sm text-muted-foreground">Loading…</div>}>
          <MultiVariateResults strategyId={strategyId} />
        </Suspense>
      </section>
    </div>
  );
}
