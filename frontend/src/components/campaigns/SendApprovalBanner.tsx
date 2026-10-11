"use client";

/** Daily send approval — the app-wide banner (web, desktop browser and the
 *  Android app, which ships this same UI). Shown while automatic messages are
 *  waiting for today's decision; links to /send-approval. Quiet on any error:
 *  the send path itself fails closed, so a missing banner never means a send. */

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { usePathname } from "next/navigation";
import { ShieldAlert } from "lucide-react";

import { getSendApproval } from "@/lib/api/sendApproval";
import { bannerText, queuedSummary, showBanner } from "@/lib/sendApproval";

export function SendApprovalBanner() {
  const pathname = usePathname();
  const { data } = useQuery({
    queryKey: ["send-approval"],
    queryFn: getSendApproval,
    refetchInterval: 5 * 60_000,
    retry: false,
  });
  if (!data || !showBanner(data) || pathname.startsWith("/send-approval")) return null;
  return (
    <div
      role="status"
      className="no-print mb-4 flex flex-col gap-2 rounded border border-warning/50 bg-card p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex items-start gap-2">
        <ShieldAlert size={18} aria-hidden="true" className="mt-0.5 shrink-0 text-warning" />
        <div>
          <p className="font-medium">{bannerText(data)}</p>
          <p className="text-muted-foreground">{queuedSummary(data)}</p>
        </div>
      </div>
      <Link
        href="/send-approval"
        className="inline-flex shrink-0 items-center justify-center rounded bg-primary px-3 py-2 text-sm font-medium text-primary-foreground"
      >
        {data.can_decide ? "Review and decide" : "View"}
      </Link>
    </div>
  );
}
