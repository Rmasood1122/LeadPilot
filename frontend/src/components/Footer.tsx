/**
 * components/Footer.tsx — footer for the public marketing pages
 * (/about, /contact, /how-it-works, /privacy, /terms).
 *
 * Server component. Not used by the dashboard, which has its own shell.
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

export function Footer({ showStatusLink = SHOW_STATUS_LINK }: { showStatusLink?: boolean } = {}) {
  // External link to status.calendarharvest.com, hidden until DNS is live.
  const status = statusPageLink(showStatusLink);
  return (
    <footer className="border-t border-white/10 px-6 py-12">
      <div className="mx-auto max-w-6xl">
        <div className="grid grid-cols-2 gap-8 sm:max-w-md">
          {COLUMNS.map((col) => (
            <nav key={col.heading} aria-label={col.heading}>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-white">{col.heading}</h2>
              <ul className="mt-4 space-y-3 text-sm text-gray-400">
                {col.links.map((link) => (
                  <li key={link.href}>
                    <Link href={link.href} className="hover:text-white">
                      {link.label}
                    </Link>
                  </li>
                ))}
                {col.heading === "Company" && status && (
                  <li>
                    <a href={status.href} className="hover:text-white" data-testid="footer-status-link">
                      {status.label}
                    </a>
                  </li>
                )}
              </ul>
            </nav>
          ))}
        </div>
        <p className="mt-10 border-t border-white/10 pt-6 text-sm text-gray-400">
          &copy; 2026 Calendarharvest. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
