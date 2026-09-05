"use client";

/** CRM route-group layout.
 *
 * Mounts the real-time provider ONCE, here rather than in the app layout, so
 * that:
 *   * a user who never opens the CRM never holds an SSE connection, and
 *   * moving between /crm/dashboard/* and /crm/table keeps the SAME
 *     connection — the App Router keeps a segment layout mounted while
 *     navigating within it, so the provider does not remount and the socket
 *     is not cycled on every tab click.
 */

import { CrmRealtimeProvider } from "@/contexts/CrmRealtimeContext";
import { CrmTabs, LiveIndicator } from "@/components/crm/CrmChrome";

export default function CrmLayout({ children }: { children: React.ReactNode }) {
  return (
    <CrmRealtimeProvider>
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-xl font-semibold">CRM</h1>
          <LiveIndicator />
        </div>
        <CrmTabs />
        {children}
      </div>
    </CrmRealtimeProvider>
  );
}
