/**
 * The home page components: HomeGate keeps the Android app / PWA landing in
 * the app, the web header offers "Open app" to a signed-in visitor without
 * redirecting, and the stage stepper is a working, keyboard-accessible tab
 * list.
 */
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace, push: vi.fn() }) }));

const restoreSession = vi.fn();
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  restoreSession: () => restoreSession(),
}));
const me = vi.fn();
vi.mock("@/lib/api/auth", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/auth")>()),
  me: () => me(),
}));
const native = vi.fn().mockReturnValue(false);
vi.mock("@/lib/platform", () => ({ isNative: () => native(), isServer: () => false }));

import { HomeGate } from "@/components/home/HomeGate";
import { HomeHeader } from "@/components/home/HomeHeader";
import { StageStepper } from "@/components/home/StageStepper";
import { STAGES } from "@/components/home/content";

const user = {
  email: "founder@agency.com", email_verified: true, identity_required: false,
  identity_complete: true, phone_verified: true, has_active_plan: true,
};

beforeEach(() => {
  replace.mockReset();
  restoreSession.mockReset().mockResolvedValue(false);
  me.mockReset().mockResolvedValue(user);
  native.mockReturnValue(false);
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener() {}, removeEventListener() {} }));
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HomeGate", () => {
  it("web: renders the home page and redirects nobody", async () => {
    render(<HomeGate><p>marketing</p></HomeGate>);
    expect(screen.getByText("marketing")).toBeTruthy();
    await act(async () => {});
    expect(replace).not.toHaveBeenCalled();
    expect(restoreSession).not.toHaveBeenCalled();
  });

  it("Android app, signed out: no marketing, straight to /login", async () => {
    native.mockReturnValue(true);
    render(<HomeGate><p>marketing</p></HomeGate>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("marketing")).toBeNull();
  });

  it("Android app, signed in: to the dashboard, as before", async () => {
    native.mockReturnValue(true);
    restoreSession.mockResolvedValue(true);
    render(<HomeGate><p>marketing</p></HomeGate>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/pipeline"));
    expect(screen.queryByText("marketing")).toBeNull();
  });

  it("installed PWA: treated as the app", async () => {
    vi.stubGlobal("matchMedia", (q: string) => ({ matches: q === "(display-mode: standalone)" }));
    render(<HomeGate><p>marketing</p></HomeGate>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
  });
});

describe("HomeHeader", () => {
  it("anonymous: Sign in and Start free, linking to the real routes", async () => {
    render(<HomeHeader />);
    await act(async () => {});
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/login");
    expect(screen.getAllByRole("link", { name: "Start free" })[0].getAttribute("href")).toBe("/signup");
    expect(screen.queryByTestId("open-app")).toBeNull();
  });

  it("signed in: Open app goes where the session belongs, and nothing redirects", async () => {
    restoreSession.mockResolvedValue(true);
    render(<HomeHeader />);
    await waitFor(() => expect(screen.getByTestId("open-app").getAttribute("href")).toBe("/pipeline"));
    expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });

  it("in the app shell it does not restore a second time (HomeGate does)", async () => {
    native.mockReturnValue(true);
    render(<HomeHeader />);
    await act(async () => {});
    expect(restoreSession).not.toHaveBeenCalled();
  });
});

describe("StageStepper", () => {
  it("is a tab list with one panel per stage, the first selected", () => {
    render(<StageStepper />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(STAGES.map((s, i) => `${i + 1}${s.name}`));
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel").getAttribute("aria-labelledby")).toBe(tabs[0].id);
    // every panel is in the HTML; only one is visible
    expect(document.querySelectorAll('[role="tabpanel"]')).toHaveLength(STAGES.length);
    expect(document.querySelectorAll('[role="tabpanel"]:not([hidden])')).toHaveLength(1);
  });

  it("click and arrow keys change the stage and move focus (roving tabindex)", () => {
    render(<StageStepper />);
    fireEvent.click(screen.getByRole("tab", { name: /Sending/ }));
    expect(screen.getByRole("tabpanel").textContent).toContain(STAGES[3].title);
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowDown" });
    const replies = screen.getByRole("tab", { name: /Replies/ });
    expect(replies.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(replies);
    expect(replies.getAttribute("tabindex")).toBe("0");
    expect(screen.getByRole("tab", { name: /Sending/ }).getAttribute("tabindex")).toBe("-1");
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "End" });
    expect(screen.getByRole("tab", { name: /Meetings/ }).getAttribute("aria-selected")).toBe("true");
  });

  it("the Next button walks the stages", () => {
    render(<StageStepper />);
    fireEvent.click(screen.getByRole("button", { name: "Next: Leads" }));
    expect(screen.getByRole("tab", { name: /Leads/ }).getAttribute("aria-selected")).toBe("true");
  });
});
