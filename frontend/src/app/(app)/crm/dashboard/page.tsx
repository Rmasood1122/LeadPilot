"use client";

/** /crm/dashboard is a container, not a screen — it lands on the overview.
 *  Client-side because this is a static export; see ../page.tsx. */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function CrmDashboardIndexPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/crm/dashboard/overview");
  }, [router]);

  return (
    <p className="text-sm text-muted-foreground" role="status">
      Opening the CRM overview…
    </p>
  );
}
