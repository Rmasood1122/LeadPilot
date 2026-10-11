/** Who sees the marketing home page at "/", and where everyone else goes.
 *
 *  "/" used to be a pure redirect (to /login, the dashboard or /check-email).
 *  It is now the public home page on the WEB, but the same static export is
 *  also the Android app (Capacitor loads out/index.html) and the installed
 *  PWA (manifest start_url "/"). Those are apps: they must land the user in
 *  the app exactly as before, never on marketing.
 *
 *  App shell = any of:
 *    - a mobile build (NEXT_PUBLIC_BUILD_TARGET mobile-dev / mobile-prod,
 *      package.json mobile:build:*), decided at BUILD time, so the exported
 *      index.html carries no marketing markup at all;
 *    - running inside Capacitor (isNative(), src/lib/platform.ts) — covers an
 *      APK built from a plain `next build` (package.json mobile:build);
 *    - an installed PWA (display-mode: standalone).
 *
 *  Pure, so every rule is unit-tested in src/tests/homeEntry.test.ts. */

import { DASHBOARD_PATH, postLoginDestination } from "./post-login";
import type { UserOut } from "./api/types";

export type HomeMode = "marketing" | "app";

export function isAppBuild(buildTarget: string | undefined): boolean {
  return (buildTarget ?? "").toLowerCase().startsWith("mobile");
}

export function homeMode(env: {
  buildTarget: string | undefined;
  native: boolean;
  standalone: boolean;
}): HomeMode {
  if (isAppBuild(env.buildTarget) || env.native || env.standalone) return "app";
  return "marketing";
}

export interface EntryDeps {
  restoreSession: () => Promise<boolean>;
  me: () => Promise<UserOut>;
  phoneDeferred: () => boolean;
  isUnverifiedError: (err: unknown) => boolean;
}

/** Where the APP sends someone who opens "/". Byte-for-byte the routing the
 *  old redirect-only page did: no session -> /login; a session -> wherever a
 *  restored session belongs (postLoginDestination without afterLogin, so no
 *  plan check); unverified -> /check-email; any other failure (API hiccup) ->
 *  the dashboard, whose Shell re-checks and surfaces the failure. */
export async function appEntryDestination(deps: EntryDeps): Promise<string> {
  if (!(await deps.restoreSession())) return "/login";
  try {
    const user = await deps.me();
    return postLoginDestination(user, { phoneDeferred: deps.phoneDeferred() });
  } catch (err) {
    return deps.isUnverifiedError(err) ? "/check-email" : DASHBOARD_PATH;
  }
}

/** For the WEB home page header: where "Open app" should go for a visitor
 *  who is already signed in, or null for an anonymous visitor (who sees
 *  "Sign in" instead). Never redirects anyone. */
export async function signedInAppLink(deps: EntryDeps): Promise<string | null> {
  let signedIn = false;
  try {
    signedIn = await deps.restoreSession();
  } catch {
    return null;
  }
  if (!signedIn) return null;
  return appEntryDestination({ ...deps, restoreSession: async () => true });
}

/** Runs before hydration, inline in the exported HTML of "/": marks <html>
 *  data-app-shell when this is the Android app or an installed PWA, so CSS
 *  hides the marketing markup and the app never flashes it while the
 *  redirect runs. Native detection mirrors @capacitor/core getPlatformId():
 *  the WebView's `androidBridge` JavaScript interface (iOS:
 *  webkit.messageHandlers.bridge) exists before any page script runs; a
 *  native window.Capacitor that already says so counts too. Plain ES5 on
 *  purpose; every failure leaves the page as it is. */
export const APP_SHELL_SCRIPT = `(function(){try{var w=window,C=w.Capacitor,k=w.webkit;var n=!!(w.androidBridge||(k&&k.messageHandlers&&k.messageHandlers.bridge)||(C&&typeof C.isNativePlatform==="function"&&C.isNativePlatform()));var s=!!(w.matchMedia&&w.matchMedia("(display-mode: standalone)").matches);if(n||s)document.documentElement.setAttribute("data-app-shell","1");}catch(e){}})();`;

export function isStandaloneDisplay(): boolean {
  try {
    return typeof window !== "undefined" && !!window.matchMedia?.("(display-mode: standalone)").matches;
  } catch {
    return false;
  }
}
