/**
 * The "Status" link to status.calendarharvest.com sits behind one constant
 * (src/lib/statusPage.ts) so it can stay hidden until DNS is live.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { Footer } from "@/components/Footer";
import { SHOW_STATUS_LINK, STATUS_PAGE_URL, statusPageLink } from "@/lib/statusPage";

describe("status page link", () => {
  it("points at the status domain", () => {
    expect(STATUS_PAGE_URL).toBe("https://status.calendarharvest.com");
    expect(statusPageLink(true)).toEqual({ href: STATUS_PAGE_URL, label: "Status" });
    expect(statusPageLink(false)).toBeNull();
  });

  it("is hidden by default until the founders confirm DNS", () => {
    expect(SHOW_STATUS_LINK).toBe(false);
    render(<Footer />);
    expect(screen.queryByTestId("footer-status-link")).toBeNull();
  });

  it("renders in the footer's Company column when switched on", () => {
    render(<Footer showStatusLink />);
    const link = screen.getByTestId("footer-status-link");
    expect(link.textContent).toBe("Status");
    expect(link.getAttribute("href")).toBe(STATUS_PAGE_URL);
    expect(link.closest("nav")?.getAttribute("aria-label")).toBe("Company");
  });
});
