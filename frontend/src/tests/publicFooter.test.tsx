/**
 * One shared footer on every public page (platform-gaps item 6), so the Legal
 * links and the Status link (when live) cannot drift between pages. /pricing
 * had its own page with no footer at all. The home page (src/app/page.tsx)
 * became a real page on 2026-10-11 (founder request): its body lives in
 * src/components/home/HomePage.tsx, which renders the same Footer. In the
 * Android app and an installed PWA "/" still renders nothing and only routes
 * (src/tests/homeEntry.test.ts, src/tests/homePage.test.tsx).
 */
import { readFileSync } from "node:fs";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

import { Footer } from "@/components/Footer";

const PUBLIC_PAGES = [
  "src/app/about/page.tsx",
  "src/app/contact/page.tsx",
  "src/app/how-it-works/page.tsx",
  "src/app/privacy/page.tsx",
  "src/app/terms/page.tsx",
  "src/app/pricing/page.tsx",
  "src/components/home/HomePage.tsx",
];

describe("shared public footer", () => {
  for (const page of PUBLIC_PAGES) {
    it(`${page} renders the shared Footer`, () => {
      const src = readFileSync(page, "utf8");
      expect(src).toContain('import { Footer } from "@/components/Footer"');
      expect(src).toMatch(/<Footer[\s/>]/);
    });
  }

  it("the home page renders the home page body behind the app-shell gate", () => {
    const src = readFileSync("src/app/page.tsx", "utf8");
    expect(src).toMatch(/<HomeGate>\s*<HomePage \/>\s*<\/HomeGate>/);
    // in the app shell the gate renders nothing and routes (old behaviour)
    const gate = readFileSync("src/components/home/HomeGate.tsx", "utf8");
    expect(gate).toContain("router.replace");
    expect(gate).toMatch(/if \(mode === "app"\) return null;/);
  });

  it("the theme tone keeps the legal links and the status link", () => {
    render(<Footer tone="theme" showStatusLink />);
    expect(screen.getByRole("link", { name: "Privacy Policy" }).getAttribute("href")).toBe("/privacy");
    expect(screen.getByRole("link", { name: "Terms of Service" }).getAttribute("href")).toBe("/terms");
    expect(screen.getByTestId("footer-status-link")).toBeTruthy();
    // drawn with theme tokens, not the dark marketing palette
    expect(screen.getByRole("contentinfo").className).toContain("border-border");
  });

  it("the default tone is unchanged for the dark marketing pages", () => {
    render(<Footer />);
    expect(screen.getByRole("contentinfo").className).toContain("border-white/10");
  });
});
