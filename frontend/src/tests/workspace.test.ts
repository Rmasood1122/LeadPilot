import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api/client";
import {
  assignableRoles, atLeast, canManage, getActiveWorkspace, setActiveWorkspace,
} from "@/lib/workspace";
import { DEFAULT_BRANDING, brandCssVars } from "@/lib/branding";

afterEach(() => {
  setActiveWorkspace(null);
  vi.unstubAllGlobals();
});

describe("role ladder", () => {
  it("mirrors the server rules", () => {
    expect(assignableRoles("owner")).toEqual(["manager", "sdr", "viewer"]);
    expect(assignableRoles("manager")).toEqual(["sdr", "viewer"]);
    expect(assignableRoles("sdr")).toEqual([]);
    expect(canManage("manager", "manager")).toBe(false);
    expect(canManage("manager", "viewer")).toBe(true);
    expect(canManage("owner", "owner")).toBe(false);
    expect(atLeast("manager", "sdr")).toBe(true);
    expect(atLeast("viewer", "sdr")).toBe(false);
    expect(atLeast(undefined, "viewer")).toBe(false);
  });
});

describe("workspace header", () => {
  it("is sent while a workspace is selected and dropped when it is gone", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    setActiveWorkspace("ws-1");
    await api("/deals");
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-Workspace-Id"]).toBe("ws-1");

    fetchMock.mockImplementationOnce(async () =>
      new Response(JSON.stringify({ detail: "workspace not found" }), { status: 404 }));
    await expect(api("/deals")).rejects.toThrow("workspace not found");
    expect(getActiveWorkspace()).toBeNull();
  });

  it("is never sent on unauthenticated calls", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    setActiveWorkspace("ws-1");
    await api("/branding?host=x", { auth: false });
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-Workspace-Id"]).toBeUndefined();
  });
});

describe("brandCssVars", () => {
  it("only overrides colours for a white-labelled brand with a valid colour", () => {
    expect(brandCssVars(DEFAULT_BRANDING)).toEqual({});
    expect(brandCssVars({ ...DEFAULT_BRANDING, white_label: true, primary_color: "blue" })).toEqual({});
    const vars = brandCssVars({ ...DEFAULT_BRANDING, white_label: true, primary_color: "#0f766e" });
    expect(vars["--primary"]).toBe("15 118 110");
    expect(vars["--primary-foreground"]).toMatch(/^\d+ \d+ \d+$/);
  });
});
