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

/** Responsive app shell: collapsible sidebar on >=md, bottom-tab bar on
 *  mobile (the M7 Capacitor wrapper ships THIS layout). Also the protected
 *  gate: no session -> /login, unverified email -> /check-email. */
export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [ready, setReady] = useState(false);

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
          <LogoMark size={22} />
          {!collapsed && <span className="font-semibold">LeadPilot</span>}
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
            <LogoMark size={22} />
            LeadPilot
          </span>
          <span className="hidden text-sm text-muted-foreground md:block">
            {NAV.find((n) => pathname.startsWith(n.href))?.label ?? ""}
          </span>
        </header>
        <main className="flex-1 p-gutter pb-20 md:pb-gutter">{children}</main>
      </div>

      {/* Bottom tabs (mobile) */}
      <nav
        aria-label="Main navigation"
        className="no-print fixed inset-x-0 bottom-0 z-10 flex border-t border-border bg-card md:hidden"
      >
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={pathname.startsWith(href) ? "page" : undefined}
            className={cn(
              "flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px]",
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
