"use client";

/**
 * "/" is the marketing home page on the web and the app's front door in the
 * Android app and an installed PWA (src/lib/homeEntry.ts explains the rule).
 *
 * In the app it renders nothing and routes exactly as the old redirect-only
 * page did. The first render uses only the build target, so the server HTML
 * and the first client render agree; the runtime checks (Capacitor,
 * display-mode) run after mount. APP_SHELL_SCRIPT in page.tsx hides the
 * marketing markup before hydration so the app never flashes it.
 */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { isUnverifiedError, me } from "@/lib/api/auth";
import { restoreSession } from "@/lib/api/client";
import { appEntryDestination, homeMode, isAppBuild, isStandaloneDisplay, type HomeMode } from "@/lib/homeEntry";
import { isPhoneDeferred } from "@/lib/identity";
import { isNative } from "@/lib/platform";

const BUILD_TARGET = process.env.NEXT_PUBLIC_BUILD_TARGET;

export function HomeGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [mode, setMode] = useState<HomeMode>(isAppBuild(BUILD_TARGET) ? "app" : "marketing");

  useEffect(() => {
    const m = homeMode({ buildTarget: BUILD_TARGET, native: isNative(), standalone: isStandaloneDisplay() });
    setMode(m);
    if (m !== "app") return;
    let mounted = true;
    appEntryDestination({ restoreSession, me, phoneDeferred: isPhoneDeferred, isUnverifiedError })
      .then((dest) => {
        if (mounted) router.replace(dest);
      })
      .catch(() => {
        if (mounted) router.replace("/login");
      });
    return () => {
      mounted = false;
    };
  }, [router]);

  if (mode === "app") return null;
  return <>{children}</>;
}
