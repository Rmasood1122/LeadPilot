/**
 * Link to the public status page: /status on this site
 * (www.calendarharvest.com/status/, src/app/status/page.tsx;
 * docs/program/STATUS_PAGE.md).
 *
 * The page is part of this static export on Vercel, so it needs no DNS record
 * and keeps loading when the API on Render is down. Trailing slash because the
 * export uses `trailingSlash: true` (next.config.js), so the file is
 * status/index.html.
 *
 * SHOW_STATUS_LINK shows "Status" in the marketing footer (Company column)
 * and an icon link in the support widget header. The optional subdomain app
 * in /status-page is no longer what this link points to.
 */
export const STATUS_PAGE_URL = "/status/";

export const SHOW_STATUS_LINK = true;

export interface StatusPageLink {
  href: string;
  label: string;
}

export function statusPageLink(show: boolean = SHOW_STATUS_LINK): StatusPageLink | null {
  return show ? { href: STATUS_PAGE_URL, label: "Status" } : null;
}
