"use client";

/** /crm has no content of its own — it lands on the overview.
 *
 * A client-side redirect rather than next.config.js `redirects`, because the
 * app is `output: 'export'`: there is no server to issue a 302, and the
 * Capacitor WebView loads these files off disk. `replace` rather than `push`
 * so the back button does not bounce between /crm and /crm/dashboard/overview.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function CrmIndexPage() {
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
