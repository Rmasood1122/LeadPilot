/**
 * The public status page (status.calendarharvest.com — a separate Vercel
 * project in /status-page; docs/program/STATUS_PAGE.md).
 *
 * SHOW_STATUS_LINK stays false until the founders have added the DNS record
 * and the page loads on its domain ("Go-live" in STATUS_PAGE.md). A link to
 * a domain that does not resolve yet would look like an outage of its own.
 * Flipping it to true shows "Status" in the marketing footer and in the
 * support widget header.
 */
export const STATUS_PAGE_URL = "https://status.calendarharvest.com";

export const SHOW_STATUS_LINK = false;

export interface StatusPageLink {
  href: string;
  label: string;
}

export function statusPageLink(show: boolean = SHOW_STATUS_LINK): StatusPageLink | null {
  return show ? { href: STATUS_PAGE_URL, label: "Status" } : null;
}
