/**
 * components/Footer.tsx — footer for the public pages
 * (/about, /contact, /how-it-works, /privacy, /terms, /pricing, /status).
 *
 * Server component. Not used by the dashboard, which has its own shell.
 * One footer everywhere so the Legal links and the Status link (when live)
 * cannot drift between pages. `tone="theme"` is for pages drawn with the app
 * theme tokens (/pricing) instead of the dark marketing palette.
 */

import Link from "next/link";

import { SHOW_STATUS_LINK, statusPageLink } from "@/lib/statusPage";

const COLUMNS = [
  {
    heading: "Company",
    links: [
      { href: "/about", label: "About" },
      { href: "/contact", label: "Contact" },
      { href: "/pricing", label: "Pricing" },
    ],
  },
  {
    heading: "Legal",
    links: [
      { href: "/privacy", label: "Privacy Policy" },
      { href: "/terms", label: "Terms of Service" },
    ],
  },
];

const TONES = {
  dark: {
    border: "border-white/10",
    heading: "text-white",
    text: "text-gray-400",
    hover: "hover:text-white",
  },
  theme: {
    border: "border-border",
    heading: "text-foreground",
    text: "text-muted-foreground",
    hover: "hover:text-foreground",
  },
} as const;

export function Footer({
  showStatusLink = SHOW_STATUS_LINK,
  tone = "dark",
}: { showStatusLink?: boolean; tone?: keyof typeof TONES } = {}) {
  // The /status page on this site (src/lib/statusPage.ts).
  const status = statusPageLink(showStatusLink);
  const t = TONES[tone];
  return (
    <footer className={`border-t ${t.border} px-6 py-12`}>
      <div className="mx-auto max-w-6xl">
        <div className="grid grid-cols-2 gap-8 sm:max-w-md">
          {COLUMNS.map((col) => (
            <nav key={col.heading} aria-label={col.heading}>
              <h2 className={`text-sm font-semibold uppercase tracking-wider ${t.heading}`}>{col.heading}</h2>
              <ul className={`mt-4 space-y-3 text-sm ${t.text}`}>
                {col.links.map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className={t.hover}>
                      {link.label}
                    </Link>
                  </li>
                ))}
                {col.heading === "Company" && status && (
                  <li>
                    <a href={status.href} className={t.hover} data-testid="footer-status-link">
                      {status.label}
                    </a>
                  </li>
                )}
              </ul>
            </nav>
          ))}
        </div>
        <p className={`mt-10 border-t ${t.border} pt-6 text-sm ${t.text}`}>
          &copy; 2026 Calendarharvest. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
