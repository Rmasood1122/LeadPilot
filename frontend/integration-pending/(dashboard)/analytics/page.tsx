// app/(dashboard)/analytics/page.tsx
// M5 analytics page + M8-C4 SendTimeCard + SubjectLineCard additions.
"use client";

import { Suspense } from "react";
import { ReplyRateChart } from "@/components/analytics/ReplyRateChart";
import { MeetingRateChart } from "@/components/analytics/MeetingRateChart";
import { OutcomesFunnel } from "@/components/analytics/OutcomesFunnel";
import { SendTimeCard } from "@/components/analytics/SendTimeCard";
import { SubjectLineCard } from "@/components/analytics/SubjectLineCard";

export default function AnalyticsPage() {
  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Analytics</h1>

      {/* Funnel */}
      <OutcomesFunnel />

      {/* Charts row */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ReplyRateChart />
        <MeetingRateChart />
      </div>

      {/* Learning insights row (C4 additions) */}
      <div>
        <h2 className="font-semibold mb-3">Learning Insights</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Suspense fallback={null}>
            <SendTimeCard />
          </Suspense>
          <Suspense fallback={null}>
            <SubjectLineCard />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
