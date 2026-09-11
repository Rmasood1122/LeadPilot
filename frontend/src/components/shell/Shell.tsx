"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut, Menu } from "lucide-react";
import { NAV } from "./nav";
import { cn } from "@/lib/utils";
import { hasSession } from "@/lib/api/client";
import { isUnverifiedError, logout, me } from "@/lib/api/auth";
import { Button } from "@/components/ui/button";
import { LogoMark } from "@/components/ui/Logo";
import { ChatWidget } from "@/components/support/ChatWidget";
import { useBranding } from "@/lib/branding";
import { WorkspaceSwitcher } from "./WorkspaceSwitcher";

/** Responsive app shell: collapsible sidebar on >=md, bottom-tab bar on
 *  mobile (the M7 Capacitor wrapper ships THIS layout). Also the protected
 *  gate: no session -> /login, unverified email -> /check-email. */
export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [ready, setReady] = useState(false);
  // Feature Group 8: a white-labelled host shows its own name and logo.
  const brand = useBranding();
  const mark = brand.white_label && brand.logo_url
    ? <img src={brand.logo_url} alt="" className="h-[22px] w-auto max-w-[88px] object-contain" />
    : <LogoMark size={22} />;

  useEffect(() => {
    if (!hasSession()) {
      router.replace("/login");
      return;
    }
    // A session is not the same as a usable account. Someone can arrive here
    // with valid tokens and an unverified address -- a bookmarked /pipeline, a
    // second tab, a restored mobile session -- and every data fetch on the
    // page would then fail with 403 EMAIL_NOT_VERIFIED, rendering a dashboard
    // full of errors with nothing explaining why.
    //
    // GET /auth/me is the cheapest request that goes through the same
    // get_current_user dependency as everything else, so it gives the same
    // answer the rest of the page would get, once, before anything renders.
    let mounted = true;
    me()
      .then((user) => {
        if (!mounted) return;
        if (user.email_verified === false) {
          router.replace(`/check-email?email=${encodeURIComponent(user.email)}`);
          return;
        }
        setReady(true);
      })
      .catch((err) => {
        if (!mounted) return;
        if (isUnverifiedError(err)) {
          router.replace("/check-email");
          return;
        }
        // Anything else -- expired refresh token, backend down -- is the
        // pre-existing behaviour: render, and let the page's own queries
        // surface the failure. Blocking on it would white-screen the app
        // every time the API hiccups.
        setReady(true);
      });
    return () => {
      mounted = false;
    };
  }, [router]);

  if (!ready) return null;

  return (
    <div className="flex min-h-dvh">
      {/* Sidebar (tablet/desktop) */}
      <aside
        className={cn(
          "no-print sticky top-0 hidden h-dvh flex-col border-r border-border bg-card md:flex",
          collapsed ? "w-16" : "w-56",
        )}
        aria-label="Main navigation"
      >
        <div className="flex items-center gap-2 p-4">
          <button
            onClick={() => setCollapsed((c) => !c)}
            aria-label="Toggle sidebar"
            className="rounded p-1 hover:bg-muted"
          >
            <Menu size={18} />
          </button>
          {/* Mark stays visible when collapsed (w-16) — the rail keeps its
              brand anchor; only the wordmark text is dropped. */}
          {mark}
          {!collapsed && <span className="font-semibold">{brand.brand_name}</span>}
        </div>
        <nav className="flex-1 space-y-1 px-2">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={pathname.startsWith(href) ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded px-3 py-2 text-sm",
                pathname.startsWith(href)
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-muted",
              )}
            >
              <Icon size={18} aria-hidden="true" />
              {!collapsed && label}
            </Link>
          ))}
        </nav>
        <div className="p-2">
          <Button
            variant="ghost"
            className="w-full justify-start gap-3"
            onClick={() => {
              logout();
              router.replace("/login");
            }}
          >
            <LogOut size={18} aria-hidden="true" />
            {!collapsed && "Log out"}
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="no-print sticky top-0 z-10 flex h-14 items-center justify-between border-b border-border bg-card px-4">
          <span className="flex items-center gap-2 font-semibold md:hidden">
            {mark}
            {brand.brand_name}
          </span>
          <span className="hidden text-sm text-muted-foreground md:block">
            {NAV.find((n) => pathname.startsWith(n.href))?.label ?? ""}
          </span>
          <WorkspaceSwitcher />
        </header>
        <main className="flex-1 p-gutter pb-20 md:pb-gutter">{children}</main>
      </div>

      {/* AI support chat (Feature 3).
          Mounted HERE, once, rather than per page: the widget has to be
          reachable from every dashboard screen, and eight pages each
          remembering to render it is eight chances to forget. It sits outside
          <main> so page content cannot scroll it away, and it is only ever
          rendered past the auth + verification gate above -- an unverified
          user hitting /support/chat would just collect 403s. */}
      <ChatWidget />

      {/* Bottom tabs (mobile).

          HORIZONTALLY SCROLLABLE since the Engagement Hub added Calendar and
          Meetings. With `flex-1` and nine items a 360px phone gives each tab
          40px, which is below the 44px minimum touch target on every platform
          guideline and puts two labels on top of each other. Each tab now has
          a 4.5rem basis and does not shrink, so on a narrow phone the bar
          scrolls and every tab stays tappable, while on a wider one they grow
          to fill the width exactly as before.

          Scrolling was chosen over dropping items into an overflow menu:
          every entry here is a top-level destination, and hiding two of them
          behind a "more" button on the platform where the product is most
          often opened is a worse answer than a bar you can swipe. */}
      <nav
        aria-label="Main navigation"
        className="no-print fixed inset-x-0 bottom-0 z-10 flex overflow-x-auto border-t border-border bg-card md:hidden"
      >
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={pathname.startsWith(href) ? "page" : undefined}
            className={cn(
              "flex flex-1 shrink-0 basis-[4.5rem] flex-col items-center gap-0.5 py-2 text-[10px]",
              pathname.startsWith(href)
                ? "text-[rgb(var(--primary))]"
                : "text-muted-foreground",
            )}
          >
            <Icon size={20} aria-hidden="true" />
            {label}
          </Link>
        ))}
      </nav>
    </div>
  );
}
