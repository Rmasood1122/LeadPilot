/** Central fetch wrapper: base URL, auth header injection, one automatic
 *  refresh-then-retry on 401, and error normalization to ApiError.
 *  Components NEVER call fetch directly — they use the domain modules +
 *  React Query hooks built on this.
 *
 * SECURITY FIX: this file used to store JWT tokens directly in
 * localStorage (its own "leadpilot.access"/"leadpilot.refresh" keys) —
 * completely bypassing src/lib/storage.ts + src/lib/auth-session.ts (the
 * sessionStorage-on-web / Capacitor-Preferences-on-native abstraction
 * that was built, documented, and tested specifically to keep tokens out
 * of localStorage). auth-session.ts's own top comment even lists the
 * exact localStorage.setItem('access_token', ...) pattern to search for
 * and replace — but its grep list used the OLD M5 key names, which
 * didn't match this file's actual keys ("leadpilot.access", not
 * "access_token"), so this file was missed by that migration entirely.
 * Now delegates to auth-session.ts so there is exactly one storage path
 * for tokens, matching what storage.test.ts already verifies. */

import {
  clearSession as clearAuthSession,
  getAccessToken,
  getAccessTokenSync,
  getRefreshToken,
  removeStoredRefreshToken,
  setAccessToken,
  setSession,
} from "../auth-session";
import { isNative } from "../platform";
import { WORKSPACE_HEADER, getActiveWorkspace, setActiveWorkspace } from "../workspace";

/** PERSISTENT SIGN-IN
 *
 *  Web: the refresh token is an HttpOnly, Secure, SameSite cookie the API sets
 *  on /auth/login, /auth/signup and /auth/refresh. Script never sees it. Every
 *  request to /auth/* is sent with `credentials: "include"` and the
 *  X-Auth-Transport header — the API reads the cookie ONLY when that header is
 *  present, which is what stops another site from driving those routes with
 *  the user's cookie (it cannot send a custom header past CORS).
 *
 *  Native (Capacitor): cookies in a WebView are unreliable across app restarts,
 *  so the refresh token stays in OS storage and travels in the request body,
 *  exactly as before.
 *
 *  Either way, restoreSession() turns "no access token in this tab" into a
 *  silent refresh, so a returning user is signed straight back in. */
export const AUTH_TRANSPORT_HEADER = "X-Auth-Transport";

export function usesCookieTransport(): boolean {
  return !isNative();
}

function authRouteInit(path: string): { headers: Record<string, string>; credentials?: RequestCredentials } {
  if (!path.startsWith("/auth/") || !usesCookieTransport()) return { headers: {} };
  return { headers: { [AUTH_TRANSPORT_HEADER]: "cookie" }, credentials: "include" };
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

/**
 * The API origin, baked in at BUILD time (static export — there is no server
 * to read an env var at runtime).
 *
 * There is deliberately NO silent production fallback. The previous
 * `?? "http://localhost:8000"` meant a build with the variable unset produced
 * a bundle that compiled, deployed green, and then sent every visitor's browser
 * to their own machine — a failure invisible to CI, to health checks and to the
 * deploying engineer. next.config.js now fails `next build` outright when the
 * variable is missing, and this throw is the second line of defence in case a
 * bundle is ever produced another way.
 *
 * The localhost default survives for `next dev` only, where it is the correct
 * value and where a missing variable is not a shipping hazard.
 */
const API_URL = process.env.NEXT_PUBLIC_API_URL;

if (!API_URL && process.env.NODE_ENV === "production") {
  throw new Error(
    "NEXT_PUBLIC_API_URL was not set at build time. This bundle cannot reach " +
      "the backend. Rebuild with NEXT_PUBLIC_API_URL set to the API origin.",
  );
}

export const BASE = API_URL ?? "http://localhost:8000";

// Refresh a minute before the access token expires, so an active user never
// has a request bounce off a 401 first. The 401 path below remains the
// backstop (a laptop that slept through the timer, a revoked session).
const PROACTIVE_REFRESH_LEAD_SECONDS = 60;
let proactiveRefreshTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleProactiveRefresh(expiresIn?: number) {
  if (typeof window === "undefined" || !expiresIn || expiresIn <= 0) return;
  if (proactiveRefreshTimer) clearTimeout(proactiveRefreshTimer);
  const delayMs = Math.max(expiresIn - PROACTIVE_REFRESH_LEAD_SECONDS, 30) * 1000;
  proactiveRefreshTimer = setTimeout(() => {
    proactiveRefreshTimer = null;
    void refreshSession();
  }, delayMs);
}

export function saveSession(tokens: {
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
}) {
  // Fire-and-forget is fine here: the access token is cached in memory
  // synchronously inside setSession, before its first await, so the caller's
  // next request already carries it.
  const native = !usesCookieTransport();
  void setSession({
    accessToken: tokens.access_token,
    // Web never stores a refresh token: the API put it in an HttpOnly cookie.
    refreshToken: native ? tokens.refresh_token : undefined,
  });
  if (!native) void removeStoredRefreshToken();
  scheduleProactiveRefresh(tokens.expires_in);
}

export function clearSession() {
  if (proactiveRefreshTimer) {
    clearTimeout(proactiveRefreshTimer);
    proactiveRefreshTimer = null;
  }
  void clearAuthSession();
}

/** Synchronous: is there an access token in THIS tab right now? A returning
 *  visitor has none until restoreSession() has run, so route guards must use
 *  restoreSession(); this stays for render-time checks that must not wait. */
export function hasSession(): boolean {
  return !!getAccessTokenSync();
}

/** Resolve to whether the user is signed in, silently restoring the session
 *  from the refresh credential when this tab has no access token yet. Safe to
 *  call from every guard at once: concurrent calls share one refresh. */
export async function restoreSession(): Promise<boolean> {
  if (getAccessTokenSync()) return true;
  if (!usesCookieTransport()) {
    const stored = await getAccessToken();
    if (stored) {
      await setAccessToken(stored); // warm the in-memory copy for sync readers
      return true;
    }
  }
  return refreshSession();
}

/** Normalize any backend/network failure into ApiError with a human
 *  detail string (FastAPI puts errors in `detail`, sometimes as a list). */
export async function normalizeError(resp: Response): Promise<ApiError> {
  let detail = `${resp.status} ${resp.statusText}`;
  try {
    const data = await resp.json();
    if (typeof data.detail === "string") detail = data.detail;
    else if (Array.isArray(data.detail)) {
      detail = data.detail
        .map((d: { loc?: unknown[]; msg?: string }) =>
          [Array.isArray(d.loc) ? d.loc.join(".") : "", d.msg]
            .filter(Boolean)
            .join(": "),
        )
        .join("; ");
    }
  } catch {
    /* non-JSON body — keep the status line */
  }
  return new ApiError(resp.status, detail);
}

let refreshInflight: Promise<boolean> | null = null;

/** Exchange the refresh credential for a new access token.
 *
 *  SINGLE-FLIGHT. The API rotates the refresh token on every use, so five
 *  requests hitting 401 at once must not become five refreshes — four of them
 *  would present an already-rotated token. They all await this one promise.
 *
 *  Only a 401 ends the session. A network error or a 5xx is transient: signing
 *  the user out because the API blipped would be the opposite of "stay signed
 *  in", so the session is kept and the caller's request fails normally. */
export function refreshSession(): Promise<boolean> {
  if (!refreshInflight) {
    refreshInflight = performRefresh().finally(() => {
      refreshInflight = null;
    });
  }
  return refreshInflight;
}

async function performRefresh(): Promise<boolean> {
  const init = authRouteInit("/auth/refresh");
  let body: string | undefined;
  if (!usesCookieTransport()) {
    const refresh = await getRefreshToken();
    if (!refresh) return false;
    body = JSON.stringify({ refresh_token: refresh });
    init.headers["Content-Type"] = "application/json";
  }
  let resp: Response;
  try {
    resp = await fetch(`${BASE}/auth/refresh`, { method: "POST", body, ...init });
  } catch {
    return false;
  }
  if (resp.status === 401) {
    clearSession();
    return false;
  }
  if (!resp.ok) return false;
  saveSession(await resp.json());
  return true;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  formData?: FormData;
  auth?: boolean; // default true
}

export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const doFetch = async () => {
    const { headers, credentials } = authRouteInit(path);
    if (!opts.formData) headers["Content-Type"] = "application/json";
    if (opts.auth !== false) {
      const token = getAccessTokenSync();
      if (token) headers["Authorization"] = `Bearer ${token}`;
      // Feature Group 8: act in the selected workspace (the server checks
      // membership and role on every request).
      const workspace = getActiveWorkspace();
      if (workspace) headers[WORKSPACE_HEADER] = workspace;
    }
    return fetch(`${BASE}${path}`, {
      method: opts.method ?? (opts.body || opts.formData ? "POST" : "GET"),
      headers,
      body: opts.formData ?? (opts.body ? JSON.stringify(opts.body) : undefined),
      ...(credentials ? { credentials } : {}),
    });
  };

  let resp = await doFetch();
  if (resp.status === 401 && opts.auth !== false && (await refreshSession())) {
    resp = await doFetch();
  }
  if (!resp.ok) {
    const error = await normalizeError(resp);
    // Removed from the selected workspace: fall back to the personal one
    // rather than failing every request from here on.
    if (resp.status === 404 && error.detail === "workspace not found") setActiveWorkspace(null);
    throw error;
  }
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}


// ── Combined-build compat export ────────────────────────────────────────────
// The M8 api modules (admin, onboarding, plans) and several M8 components
// were written against an `apiClient` object.  The M5 equivalent is the
// module-level `api<T>()` function — provide a thin adapter here so all
// call sites compile without changes.
//
// FIXED (feature expansion): post/put/patch used to pass
// `body: JSON.stringify(body)`, and api() stringifies `body` AGAIN -- so every
// write went out as a JSON *string* ("\"{...}\"") and FastAPI answered 422.
// Every apiClient write in the app was broken. And seven modules read
// `.then((r) => r.data)` off a result that is already the parsed body, so
// every apiClient read rendered `undefined` (the admin users / suppression /
// task-error pages, the plan card, onboarding, the send-time card). The body
// is now passed through untouched, and those `.data` reads were removed at
// the call sites.
// `T = any` keeps the typing those call sites always had: they were written
// against `.then((r: any) => ...)`, so their data was `any` all along.
type Loose = any;
export const apiClient = {
  get:    <T = Loose>(path: string, opts?: RequestOptions) => api<T>(path, { method: "GET",    ...opts }),
  post:   <T = Loose>(path: string, body?: unknown, opts?: RequestOptions) =>
    api<T>(path, { method: "POST",   body, ...opts }),
  put:    <T = Loose>(path: string, body?: unknown, opts?: RequestOptions) =>
    api<T>(path, { method: "PUT",    body, ...opts }),
  patch:  <T = Loose>(path: string, body?: unknown, opts?: RequestOptions) =>
    api<T>(path, { method: "PATCH",  body, ...opts }),
  delete: <T = Loose>(path: string, opts?: RequestOptions) => api<T>(path, { method: "DELETE", ...opts }),
};