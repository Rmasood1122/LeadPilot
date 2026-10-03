import { api, saveSession, clearSession, usesCookieTransport, ApiError } from "./client";
import { getRefreshToken } from "../auth-session";
import { resetAuthStore } from "../stores/authStore";
import type { TokenBundle, UserOut } from "./types";

/** Create an account.
 *
 * Returns the whole bundle, not just the user, because the caller has to
 * branch on `verification_email_sent`: the account exists either way, but if
 * the mail transport was down the screen must offer "resend" immediately
 * rather than telling the user to check an inbox that will stay empty.
 *
 * The session IS saved even though the account cannot use it yet. Those tokens
 * are what let the check-email screen exist as a signed-in page, and they start
 * working the instant the link is clicked — no second login.
 */
export async function signup(
  email: string,
  password: string,
): Promise<TokenBundle> {
  const bundle = await api<TokenBundle>("/auth/signup", {
    body: { email, password },
    auth: false,
  });
  saveSession(bundle);
  return bundle;
}

/** `rememberMe` ("keep me signed in", default on): a 30-day session that
 *  survives closing the browser. Off: the session ends with the browser. */
export async function login(email: string, password: string, rememberMe = true): Promise<UserOut> {
  const bundle = await api<TokenBundle>("/auth/login", {
    body: { email, password, remember_me: rememberMe },
    auth: false,
  });
  saveSession(bundle);
  return bundle.user;
}

/** Ask for a fresh verification link.
 *
 * Always resolves for any syntactically valid address — the backend answers
 * 202 whether or not an account exists, deliberately, so this cannot be used
 * to discover who has an account. The UI must therefore show the same
 * confirmation regardless.
 */
export async function resendVerification(email: string): Promise<void> {
  await api<{ status: string; detail: string }>("/auth/resend-verification", {
    body: { email },
    auth: false,
  });
}

/** The exact detail string the backend sends when an account is unverified.
 *  Mirrors EMAIL_NOT_VERIFIED in app/services/auth.py. */
export const EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED";

/** True when a failed request failed *because* the account is unverified. */
export function isUnverifiedError(err: unknown): boolean {
  return (
    err instanceof ApiError &&
    err.status === 403 &&
    err.detail === EMAIL_NOT_VERIFIED
  );
}

/** Sign out for real: the API revokes the session and clears the HttpOnly
 *  cookie (script cannot). Local state is cleared even when that call fails —
 *  offline, API down — so the button always works on this device. */
export async function logout(): Promise<void> {
  try {
    const refresh = usesCookieTransport() ? null : await getRefreshToken();
    await api<void>("/auth/logout", {
      method: "POST",
      body: refresh ? { refresh_token: refresh } : {},
      auth: false,
    });
  } catch {
    /* signing out locally is still correct */
  } finally {
    clearSession();
    resetAuthStore();
    localStorage.removeItem("leadpilot.theme");
  }
}

export function me(): Promise<UserOut> {
  return api<UserOut>("/auth/me");
}
