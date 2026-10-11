/**
 * The "Status" link sits behind one constant (src/lib/statusPage.ts).
 *
 * Contract change (2026-10-11): the status page moved from the never-deployed
 * status.calendarharvest.com subdomain to /status on the main site
 * (www.calendarharvest.com/status/, same Vercel project, no DNS needed), so
 * the link is a same-site path and is shown by default.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { Footer } from "@/components/Footer";
import { SHOW_STATUS_LINK, STATUS_PAGE_URL, statusPageLink } from "@/lib/statusPage";

describe("status page link", () => {
  it("points at the /status page of the main site (trailing slash: static export)", () => {
    expect(STATUS_PAGE_URL).toBe("/status/");
    expect(statusPageLink(true)).toEqual({ href: STATUS_PAGE_URL, label: "Status" });
    expect(statusPageLink(false)).toBeNull();
  });

  it("is shown by default", () => {
    expect(SHOW_STATUS_LINK).toBe(true);
    render(<Footer />);
    const link = screen.getByTestId("footer-status-link");
    expect(link.getAttribute("href")).toBe("/status/");
  });

  it("can still be switched off", () => {
    render(<Footer showStatusLink={false} />);
    expect(screen.queryByTestId("footer-status-link")).toBeNull();
  });

  it("renders in the footer's Company column", () => {
    render(<Footer showStatusLink />);
    const link = screen.getByTestId("footer-status-link");
    expect(link.textContent).toBe("Status");
    expect(link.getAttribute("href")).toBe(STATUS_PAGE_URL);
    expect(link.closest("nav")?.getAttribute("aria-label")).toBe("Company");
  });
});
