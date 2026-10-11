// app/(dashboard)/page.tsx
// M5 dashboard page (parked, not built). The M8-C5 OnboardingChecklist it used
// to embed was deleted (product defect #22: never mounted, and nothing marks
// onboarding steps complete); see docs/program/fixes/product-defects.md.
"use client";

import { KanbanPipeline } from "@/components/pipeline/KanbanPipeline";
import { CampaignSummaryRow } from "@/components/campaigns/CampaignSummaryRow";
import { QuickStats } from "@/components/analytics/QuickStats";

export default function DashboardPage() {
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

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
