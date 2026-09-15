/**
 * Persistent sign-in on the client (lib/api/client.ts, lib/api/auth.ts).
 *
 * Web: the refresh token is an HttpOnly cookie — every /auth/* call must send
 * credentials and the X-Auth-Transport header, and no refresh token may ever
 * land in script-readable storage. Native: body transport, as before.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mockPreferences = {
  get: vi.fn().mockResolvedValue({ value: null }),
  set: vi.fn().mockResolvedValue(undefined),
  remove: vi.fn().mockResolvedValue(undefined),
  clear: vi.fn().mockResolvedValue(undefined),
};
vi.mock("@capacitor/preferences", () => ({ Preferences: mockPreferences }));

const mockIsNativePlatform = vi.fn().mockReturnValue(false);
vi.mock("@capacitor/core", () => ({
  Capacitor: { isNativePlatform: mockIsNativePlatform, getPlatform: () => "web" },
}));

const fetchMock = vi.fn();

function reply(status: number, body: unknown = {}) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: String(status),
    json: async () => body,
  } as Response);
}

const user = { id: "u1", email: "founder@agency.com", plan: "free", has_active_plan: false };

async function loadClient() {
  vi.resetModules();
  return import("@/lib/api/client");
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  mockIsNativePlatform.mockReturnValue(false);
  mockPreferences.get.mockResolvedValue({ value: null });
  mockPreferences.set.mockClear();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("restoreSession — web (HttpOnly cookie)", () => {
  it("silently refreshes from the cookie when this tab has no access token", async () => {
    fetchMock.mockReturnValueOnce(reply(200, { user, access_token: "fresh-access" }));
    const client = await loadClient();

    expect(await client.restoreSession()).toBe(true);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/auth\/refresh$/);
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.headers["X-Auth-Transport"]).toBe("cookie");
    expect(init.body).toBeUndefined();
    expect(sessionStorage.getItem("ch_access_token")).toBe("fresh-access");
    expect(client.hasSession()).toBe(true);
  });

  it("never stores a refresh token in script-readable storage", async () => {
    sessionStorage.setItem("ch_refresh_token", "left-by-an-old-build");
    fetchMock.mockReturnValueOnce(
      reply(200, { user, access_token: "a", refresh_token: "should-not-be-kept" }),
    );
    const client = await loadClient();
    await client.restoreSession();
    await Promise.resolve();
    expect(sessionStorage.getItem("ch_refresh_token")).toBeNull();
    expect(localStorage.getItem("ch_refresh_token")).toBeNull();
  });

  it("does not call the API when the tab already has an access token", async () => {
    sessionStorage.setItem("ch_access_token", "existing");
    const client = await loadClient();
    expect(await client.restoreSession()).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shares one refresh between concurrent guards", async () => {
    fetchMock.mockReturnValue(reply(200, { user, access_token: "a" }));
    const client = await loadClient();
    const results = await Promise.all([
      client.restoreSession(), client.restoreSession(), client.restoreSession(),
    ]);
    expect(results).toEqual([true, true, true]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reports signed out when there is no live session", async () => {
    fetchMock.mockReturnValueOnce(reply(401, { detail: "missing refresh token" }));
    const client = await loadClient();
    expect(await client.restoreSession()).toBe(false);
    expect(client.hasSession()).toBe(false);
  });

  it("keeps the session through a transient API failure", async () => {
    sessionStorage.setItem("ch_access_token", "still-good");
    fetchMock.mockReturnValueOnce(reply(503));
    const client = await loadClient();
    expect(await client.refreshSession()).toBe(false);
    expect(sessionStorage.getItem("ch_access_token")).toBe("still-good");

    fetchMock.mockRejectedValueOnce(new TypeError("network down"));
    expect(await client.refreshSession()).toBe(false);
    expect(sessionStorage.getItem("ch_access_token")).toBe("still-good");
  });

  it("refreshes in the background shortly before the access token expires", async () => {
    vi.useFakeTimers();
    const client = await loadClient();
    fetchMock.mockReturnValue(reply(200, { user, access_token: "next", expires_in: 900 }));
    client.saveSession({ access_token: "first", expires_in: 120 });

    await vi.advanceTimersByTimeAsync(59_000);
    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/auth\/refresh$/);
  });

  it("retries a request once after refreshing on 401", async () => {
    sessionStorage.setItem("ch_access_token", "expired");
    fetchMock
      .mockReturnValueOnce(reply(401, { detail: "token expired" }))
      .mockReturnValueOnce(reply(200, { user, access_token: "renewed" }))
      .mockReturnValueOnce(reply(200, { ok: true }));
    const client = await loadClient();

    await expect(client.api("/strategies")).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer renewed");
    // A non-auth route never sends the cookie.
    expect(fetchMock.mock.calls[2][1].credentials).toBeUndefined();
  });
});

describe("restoreSession — native (body transport)", () => {
  // An in-memory stand-in for lib/storage. The real native adapter lazy-imports
  // @capacitor/preferences on every call, and when two of those imports race
  // (setSession writes two keys at once) Vitest's mocker hands the second one
  // the REAL module, whose web fallback writes to localStorage. That is a
  // harness artifact, not app behaviour; storage.test.ts covers the adapter
  // itself. Here only what the client stores matters.
  const nativeStore = new Map<string, string>();

  beforeEach(() => {
    nativeStore.clear();
    vi.doMock("@/lib/storage", () => ({
      storage: {
        get: async (key: string) => nativeStore.get(key) ?? null,
        set: async (key: string, value: string) => void nativeStore.set(key, value),
        remove: async (key: string) => void nativeStore.delete(key),
        clear: async () => nativeStore.clear(),
      },
    }));
  });

  afterEach(() => {
    vi.doUnmock("@/lib/storage");
  });

  it("sends the stored refresh token in the body and keeps the rotated one", async () => {
    mockIsNativePlatform.mockReturnValue(true);
    nativeStore.set("ch_refresh_token", "native-refresh");
    fetchMock.mockReturnValueOnce(
      reply(200, { user, access_token: "a", refresh_token: "rotated-refresh" }),
    );
    const client = await loadClient();

    expect(await client.restoreSession()).toBe(true);
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ refresh_token: "native-refresh" });
    expect(init.credentials).toBeUndefined();
    expect(init.headers["X-Auth-Transport"]).toBeUndefined();
    await vi.waitFor(() => expect(nativeStore.get("ch_refresh_token")).toBe("rotated-refresh"));
    expect(nativeStore.get("ch_access_token")).toBe("a");
    expect(client.hasSession()).toBe(true);
  });

  it("reuses a stored access token without calling the API", async () => {
    mockIsNativePlatform.mockReturnValue(true);
    nativeStore.set("ch_access_token", "stored-access");
    const client = await loadClient();

    expect(await client.restoreSession()).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(client.hasSession()).toBe(true);
  });
});

describe("login and logout", () => {
  it("login sends keep-me-signed-in and the cookie transport", async () => {
    fetchMock.mockReturnValueOnce(reply(200, { user, access_token: "a" }));
    await loadClient();
    const { login } = await import("@/lib/api/auth");

    const signedIn = await login("founder@agency.com", "pw", false);

    expect(signedIn.has_active_plan).toBe(false);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/auth\/login$/);
    expect(JSON.parse(init.body)).toEqual({
      email: "founder@agency.com", password: "pw", remember_me: false,
    });
    expect(init.credentials).toBe("include");
    expect(init.headers["X-Auth-Transport"]).toBe("cookie");
  });

  it("logout revokes the server session and clears local state", async () => {
    sessionStorage.setItem("ch_access_token", "a");
    fetchMock.mockReturnValueOnce(reply(204));
    const client = await loadClient();
    const { logout } = await import("@/lib/api/auth");

    await logout();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/auth\/logout$/);
    expect(init.credentials).toBe("include");
    expect(client.hasSession()).toBe(false);
  });

  it("logout still signs out locally when the API is unreachable", async () => {
    sessionStorage.setItem("ch_access_token", "a");
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    const client = await loadClient();
    const { logout } = await import("@/lib/api/auth");

    await logout();
    expect(client.hasSession()).toBe(false);
  });
});
