/**
 * Forgotten-password reset (docs/features/password-reset.md): the pure rules,
 * the two pages, and the "Forgot password?" link on sign-in.
 */
import { readFileSync } from "node:fs";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import React from "react";

const requestPasswordReset = vi.fn();
const confirmPasswordReset = vi.fn();
const clearSession = vi.fn();

vi.mock("@/lib/api/auth", () => ({
  requestPasswordReset: (...a: unknown[]) => requestPasswordReset(...a),
  confirmPasswordReset: (...a: unknown[]) => confirmPasswordReset(...a),
}));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return { ...real, clearSession: () => clearSession() };
});

import { ApiError } from "@/lib/api/client";
import {
  REQUEST_SENT_MESSAGE,
  readResetToken,
  requestErrorMessage,
  resetErrorMessage,
  validateNewPassword,
} from "@/lib/passwordReset";
import ForgotPasswordPage from "@/app/(auth)/forgot-password/page";
import ResetPasswordPage from "@/app/(auth)/reset-password/page";

const TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcd";

beforeEach(() => {
  requestPasswordReset.mockReset();
  confirmPasswordReset.mockReset();
  clearSession.mockReset();
});
afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

describe("readResetToken", () => {
  it("reads the token from the fragment", () => {
    expect(readResetToken(`#token=${TOKEN}`)).toBe(TOKEN);
  });
  it("accepts a query string as a fallback", () => {
    expect(readResetToken("", `?token=${TOKEN}`)).toBe(TOKEN);
  });
  it("rejects missing, short or odd tokens", () => {
    expect(readResetToken("")).toBeNull();
    expect(readResetToken("#token=short")).toBeNull();
    expect(readResetToken("#token=has%20space%20in%20it-and-more-chars")).toBeNull();
  });
});

describe("validateNewPassword", () => {
  it("mirrors the server rules", () => {
    expect(validateNewPassword("short", "short")).toMatch(/at least 8/);
    expect(validateNewPassword("x".repeat(257), "x".repeat(257))).toMatch(/256/);
    expect(validateNewPassword("long-enough-1", "long-enough-2")).toMatch(/do not match/);
    expect(validateNewPassword("long-enough-1", "long-enough-1")).toBeNull();
  });
});

describe("error messages", () => {
  it("request: 429 says wait; anything else is generic (never 'no such account')", () => {
    expect(requestErrorMessage(new ApiError(429, "x"))).toMatch(/Wait a few minutes/);
    expect(requestErrorMessage(new Error("network"))).toMatch(/Could not send/);
  });
  it("confirm: a dead link gets one message whatever the reason", () => {
    expect(resetErrorMessage(new ApiError(400, "anything"))).toBe(
      "This reset link is invalid or has expired. Request a new one.");
    expect(resetErrorMessage(new ApiError(429, "x"))).toMatch(/Too many attempts/);
  });
});

describe("forgot-password page", () => {
  it("shows the same confirmation after any successful request", async () => {
    requestPasswordReset.mockResolvedValue(undefined);
    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: " who@x.io " } });
    fireEvent.click(screen.getByRole("button", { name: /email me a reset link/i }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe(REQUEST_SENT_MESSAGE));
    expect(requestPasswordReset).toHaveBeenCalledWith("who@x.io");
  });

  it("shows the rate-limit message on 429", async () => {
    requestPasswordReset.mockRejectedValue(new ApiError(429, "rate_limit_exceeded"));
    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "who@x.io" } });
    fireEvent.click(screen.getByRole("button", { name: /email me a reset link/i }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/Wait a few minutes/));
  });
});

describe("reset-password page", () => {
  it("reads the token, strips it from the address bar, and resets", async () => {
    window.history.replaceState(null, "", `/reset-password#token=${TOKEN}`);
    confirmPasswordReset.mockResolvedValue(undefined);
    render(<ResetPasswordPage />);
    await waitFor(() => expect(screen.getByLabelText("New password")).toBeTruthy());
    expect(window.location.hash).toBe("");
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "new-password-9" } });
    fireEvent.change(screen.getByLabelText("Repeat new password"), { target: { value: "new-password-9" } });
    fireEvent.click(screen.getByRole("button", { name: /set new password/i }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/signed out on every device/));
    expect(screen.getByRole("status").textContent).toMatch(/API keys have been revoked/);
    expect(confirmPasswordReset).toHaveBeenCalledWith(TOKEN, "new-password-9");
    expect(clearSession).toHaveBeenCalled();
  });

  it("checks the rules before calling the API", async () => {
    window.history.replaceState(null, "", `/reset-password#token=${TOKEN}`);
    render(<ResetPasswordPage />);
    await waitFor(() => expect(screen.getByLabelText("New password")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "new-password-9" } });
    fireEvent.change(screen.getByLabelText("Repeat new password"), { target: { value: "different-99" } });
    fireEvent.click(screen.getByRole("button", { name: /set new password/i }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/do not match/));
    expect(confirmPasswordReset).not.toHaveBeenCalled();
  });

  it("explains a dead link and offers a new one", async () => {
    window.history.replaceState(null, "", `/reset-password#token=${TOKEN}`);
    confirmPasswordReset.mockRejectedValue(new ApiError(400, "x"));
    render(<ResetPasswordPage />);
    await waitFor(() => expect(screen.getByLabelText("New password")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "new-password-9" } });
    fireEvent.change(screen.getByLabelText("Repeat new password"), { target: { value: "new-password-9" } });
    fireEvent.click(screen.getByRole("button", { name: /set new password/i }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/invalid or has expired/));
    expect(screen.getByRole("link", { name: /request a new link/i }).getAttribute("href"))
      .toBe("/forgot-password");
    expect(clearSession).not.toHaveBeenCalled();
  });

  it("a link without a token says so", async () => {
    window.history.replaceState(null, "", "/reset-password");
    render(<ResetPasswordPage />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/incomplete/));
  });
});

describe("profile page", () => {
  it("says a password change also revokes API keys (the server does)", () => {
    const src = readFileSync("src/app/(app)/profile/page.tsx", "utf8");
    expect(src).toMatch(/signs you out on every device and revokes your\s+personal API keys/);
  });
});

describe("sign-in page", () => {
  it("links to forgot-password", () => {
    const src = readFileSync("src/app/(auth)/login/page.tsx", "utf8");
    expect(src).toContain('href="/forgot-password"');
    expect(src).toContain("Forgot password?");
  });
});
