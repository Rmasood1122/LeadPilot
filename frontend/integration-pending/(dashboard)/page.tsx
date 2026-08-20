// app/(dashboard)/page.tsx
// M5 dashboard page + M8-C5 OnboardingChecklist addition.
// Checklist is shown when completed_count < 3; collapses/dismisses itself.
"use client";

import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";
import { OnboardingChecklist } from "@/components/onboarding/OnboardingChecklist";
import { KanbanPipeline } from "@/components/pipeline/KanbanPipeline";
import { CampaignSummaryRow } from "@/components/campaigns/CampaignSummaryRow";
import { QuickStats } from "@/components/analytics/QuickStats";

export default function DashboardPage() {
  const { data: onboarding } = useQuery({
    queryKey: ["onboarding-state"],
    queryFn: () => apiClient.get("/onboarding/state").then((r) => r.data),
    staleTime: 60_000,
  });

  const showChecklist =
    onboarding && !onboarding.all_complete && onboarding.completed_count < 3;

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Onboarding checklist — only for new users (< 3 steps done) */}
      {showChecklist && (
        <Suspense fallback={null}>
          <OnboardingChecklist />
        </Suspense>
      )}

      {/* Quick stats row */}
      <QuickStats />

      {/* Active campaigns */}
      <section className="space-y-3">
        <h2 className="font-semibold">Active Campaigns</h2>
        <CampaignSummaryRow />
      </section>

      {/* Lead pipeline kanban */}
      <section className="space-y-3">
        <h2 className="font-semibold">Lead Pipeline</h2>
        <KanbanPipeline />
      </section>
    </div>
  );
}
