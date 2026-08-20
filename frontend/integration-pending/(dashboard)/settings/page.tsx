// app/(dashboard)/settings/page.tsx
// M5 settings page + M8-C5 PlanCard addition.
"use client";

import { Suspense } from "react";
import { IntegrationsSection } from "@/components/settings/IntegrationsSection";
import { ThemeSection } from "@/components/settings/ThemeSection";
import { AccountSection } from "@/components/settings/AccountSection";
import { PlanCard } from "@/components/settings/PlanCard";

export default function SettingsPage() {
  return (
    <div className="p-6 space-y-8 max-w-2xl">
      <h1 className="text-2xl font-bold">Settings</h1>

      {/* Plan information (C5 addition) */}
      <section className="space-y-3">
        <h2 className="font-semibold text-lg">Plan</h2>
        <Suspense fallback={null}>
          <PlanCard />
        </Suspense>
      </section>

      {/* Account */}
      <section className="space-y-3">
        <h2 className="font-semibold text-lg">Account</h2>
        <AccountSection />
      </section>

      {/* Integrations */}
      <section className="space-y-3">
        <h2 className="font-semibold text-lg">Integrations</h2>
        <IntegrationsSection />
      </section>

      {/* Appearance */}
      <section className="space-y-3">
        <h2 className="font-semibold text-lg">Appearance</h2>
        <ThemeSection />
      </section>
    </div>
  );
}
