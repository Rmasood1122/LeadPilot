"use client";

/** Shared CRM chrome: the tab strip, the strategy scope picker, and the
 *  live-connection indicator.
 *
 * The live indicator is not decoration. The whole feature rests on a stream
 * that can legitimately be down (Redis restarting, the kill switch on, a
 * phone that just came back from the background), and when it is, the page
 * is being refreshed by a 60-second poll instead. A user looking at a number
 * needs to know which of those they are seeing — a dashboard that silently
 * degrades from "live" to "up to a minute old" while still looking live is
 * the kind of thing people make decisions on and then get burned by.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { listStrategies } from "@/lib/api/strategies";
import { useCrmRealtime } from "@/contexts/CrmRealtimeContext";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/crm/dashboard/overview", label: "Overview" },
  { href: "/crm/dashboard/leads", label: "Lead analytics" },
  { href: "/crm/dashboard/campaigns", label: "Campaigns" },
  { href: "/crm/dashboard/activity", label: "Activity" },
  { href: "/crm/table", label: "Table" },
];

export function CrmTabs() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="CRM sections"
      className="flex gap-1 overflow-x-auto border-b border-border"
    >
      {TABS.map((tab) => {
        // trailingSlash: true in next.config.js, so the live pathname is
        // "/crm/table/" — a strict equality check would never match.
        const active = pathname.replace(/\/$/, "") === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors",
              active
                ? "border-[rgb(var(--primary))] font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function LiveIndicator() {
  const { state } = useCrmRealtime();

  const config = {
    open: { label: "Live", dot: "bg-[rgb(var(--success))]", title: "Streaming updates as they happen." },
    connecting: { label: "Connecting", dot: "bg-[rgb(var(--warning))]", title: "Opening the live connection." },
    reconnecting: { label: "Reconnecting", dot: "bg-[rgb(var(--warning))]", title: "Live connection dropped. Refreshing every 60s until it is back." },
    offline: { label: "Polling", dot: "bg-muted-foreground", title: "Real-time is unavailable. This page refreshes every 60 seconds." },
    idle: { label: "Idle", dot: "bg-muted-foreground", title: "Not connected." },
  }[state];

  return (
    <span
      className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
      title={config.title}
      aria-live="polite"
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          config.dot,
          state === "open" && "animate-pulse",
        )}
        aria-hidden="true"
      />
      {config.label}
    </span>
  );
}

/** Scope picker. "All strategies" is the default because the CRM is an
 *  account-level view — the per-strategy screens already exist at
 *  /campaigns and /analytics. */
export function StrategyScope({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const { data } = useQuery({
    queryKey: ["strategies"],
    queryFn: listStrategies,
  });

  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="sr-only">Strategy</span>
      <select
        className="rounded border border-border bg-card px-2 py-1 text-sm text-foreground"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-label="Strategy scope"
      >
        <option value="">All strategies</option>
        {data?.map((strategy) => (
          <option key={strategy.id} value={strategy.id}>
            {(strategy as unknown as { product_name?: string }).product_name ??
              strategy.id.slice(0, 8)}
          </option>
        ))}
      </select>
    </label>
  );
}
