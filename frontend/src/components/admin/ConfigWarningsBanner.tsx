"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { listConfigWarnings } from "@/lib/api/systemAdmin";

/** Shown at the top of every admin page while the deployment has a
 *  misconfiguration only an operator can fix (GET /admin/config-warnings). */
export function ConfigWarningsBanner() {
  const { data } = useQuery({
    queryKey: ["admin", "config-warnings"],
    queryFn: listConfigWarnings,
    staleTime: 60_000,
  });
  if (!data || data.length === 0) return null;
  return (
    <div className="mb-4 space-y-2">
      {data.map((w) => (
        <div key={w.key} role="alert"
             className="flex gap-2 rounded border border-warning bg-card p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden="true" />
          <p>{w.message}</p>
        </div>
      ))}
    </div>
  );
}
