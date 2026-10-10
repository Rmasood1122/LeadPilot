"use client";

/** F07 — Usage & spend: the account's monthly spend against its own cap,
 *  data credits, alerts, and forecast vs actual for recent runs. */

import Link from "next/link";

import { SpendGuardPanel } from "@/components/analytics/SpendGuardPanel";

export default function UsagePage() {
  return (
    <div className="space-y-6">
      <div>
        <Link href="/analytics" className="text-xs text-muted-foreground hover:underline">
          ← Analytics
        </Link>
        <h1 className="text-xl font-semibold">Usage &amp; spend</h1>
      </div>
      <SpendGuardPanel />
    </div>
  );
}
