"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isUnverifiedError, me } from "@/lib/api/auth";
import { restoreSession } from "@/lib/api/client";
import { isPhoneDeferred } from "@/lib/identity";
import { DASHBOARD_PATH, postLoginDestination } from "@/lib/post-login";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    let mounted = true;
    (async () => {
      if (!(await restoreSession())) {
        if (mounted) router.replace("/login");
        return;
      }
      try {
        const user = await me();
        if (mounted) router.replace(postLoginDestination(user, { phoneDeferred: isPhoneDeferred() }));
      } catch (err) {
        // Unverified -> explain; anything else (API hiccup) -> the dashboard,
        // whose Shell re-checks and whose pages surface the failure.
        if (mounted) router.replace(isUnverifiedError(err) ? "/check-email" : DASHBOARD_PATH);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [router]);
  return null;
}
