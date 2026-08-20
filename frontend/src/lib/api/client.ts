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
  getAccessTokenSync,
  getRefreshToken,
  setSession,
} from "../auth-session";

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

export function saveSession(tokens: { access_token: string; refresh_token: string }) {
  // Fire-and-forget is fine here: callers (login/signup) already await the
  // network request before this runs, and storage.set() on web is a
  // synchronous sessionStorage write wrapped in a resolved promise — by
  // the time the caller's next `await` (or the redirect) runs, it's done.
  void setSession({
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
  });
}

export function clearSession() {
  void clearAuthSession();
}

/** Synchronous by necessity — several call sites (route guards run in
 * layout effects, before any async storage read could resolve) need an
 * immediate answer. Uses auth-session.ts's documented sync shim, which
 * reads sessionStorage directly on web. On native this returns false even
 * when a session exists (Preferences is native-async-only) — a known gap;
 * TODO: migrate Shell.tsx / app/page.tsx / authStore.ts / ThemeProvider.tsx
 * to the async hasSession() in auth-session.ts for correct native behavior. */
export function hasSession(): boolean {
  return !!getAccessTokenSync();
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

async function tryRefresh(): Promise<boolean> {
  const refresh = await getRefreshToken();
  if (!refresh) return false;
  const resp = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!resp.ok) {
    clearSession();
    return false;
  }
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
    const headers: Record<string, string> = {};
    if (!opts.formData) headers["Content-Type"] = "application/json";
    if (opts.auth !== false) {
      const token = getAccessTokenSync();
      if (token) headers["Authorization"] = `Bearer ${token}`;
    }
    return fetch(`${BASE}${path}`, {
      method: opts.method ?? (opts.body || opts.formData ? "POST" : "GET"),
      headers,
      body: opts.formData ?? (opts.body ? JSON.stringify(opts.body) : undefined),
    });
  };

  let resp = await doFetch();
  if (resp.status === 401 && opts.auth !== false && (await tryRefresh())) {
    resp = await doFetch();
  }
  if (!resp.ok) throw await normalizeError(resp);
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}


// ── Combined-build compat export ────────────────────────────────────────────
// The M8 api modules (admin, onboarding, plans) and several M8 components
// were written against an `apiClient` object.  The M5 equivalent is the
// module-level `api<T>()` function — provide a thin adapter here so all
// call sites compile without changes.
export const apiClient = {
  get:    <T>(path: string, opts?: RequestOptions) => api<T>(path, { method: "GET",    ...opts }),
  post:   <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    api<T>(path, { method: "POST",   body: JSON.stringify(body), ...opts }),
  put:    <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    api<T>(path, { method: "PUT",    body: JSON.stringify(body), ...opts }),
  patch:  <T>(path: string, body?: unknown, opts?: RequestOptions) =>
    api<T>(path, { method: "PATCH",  body: JSON.stringify(body), ...opts }),
  delete: <T>(path: string, opts?: RequestOptions) => api<T>(path, { method: "DELETE", ...opts }),
};