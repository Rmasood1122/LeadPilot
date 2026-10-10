/** Shared fixtures for the status-page data-layer tests. Offline: every
 * network call goes through a fake `fetch`. */
import { MONITOR_NAMES, type MonitorRole } from "../lib/config.ts";

export const NOW = new Date("2026-10-11T12:00:00Z");
export const KEY = "ur-readonly-SECRET-key-123";

export interface Call {
  url: string;
  init: RequestInit | undefined;
}

type Responder = (url: string, init?: RequestInit) => Response | Promise<Response>;

/** A fetch double that records calls and routes by URL prefix. */
export function fakeFetch(routes: Record<string, Responder>): { fetch: typeof fetch; calls: Call[] } {
  const calls: Call[] = [];
  const impl = async (input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    calls.push({ url, init });
    for (const [prefix, respond] of Object.entries(routes)) {
      if (url.startsWith(prefix)) return respond(url, init);
    }
    throw new TypeError(`fetch failed: no route for ${url}`);
  };
  return { fetch: impl as typeof fetch, calls };
}

export const refused: Responder = () => {
  throw new TypeError("fetch failed: connect ECONNREFUSED 127.0.0.1:8000");
};

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

/** UptimeRobot status codes: 2 up, 9 down, 0 paused. */
export function monitor(role: MonitorRole, status: number, opts: { uptime?: string; created?: number; ratio?: string } = {}) {
  return {
    id: Math.floor(Math.random() * 1e6),
    friendly_name: MONITOR_NAMES[role] as string,
    status,
    create_datetime: opts.created ?? 1_600_000_000,
    custom_uptime_ranges: Array.from({ length: 90 }, () => opts.uptime ?? "100.000").join("-"),
    custom_uptime_ratio: opts.ratio ?? "99.990",
  };
}

export function allMonitors(overrides: Partial<Record<MonitorRole, number>> = {}) {
  const roles = Object.keys(MONITOR_NAMES) as MonitorRole[];
  return { stat: "ok", monitors: roles.map((r) => monitor(r, overrides[r] ?? 2)) };
}

export function backendBody(overrides: Record<string, string> = {}) {
  const ids = ["api", "background-processing", "ai-features", "booking-pages"];
  const names: Record<string, string> = {
    api: "API",
    "background-processing": "Background processing",
    "ai-features": "AI features",
    "booking-pages": "Booking pages",
  };
  return {
    components: ids.map((id) => ({
      id,
      name: names[id],
      status: overrides[id] ?? "operational",
      checked_at: "2026-10-11T11:59:40Z",
    })),
  };
}

export const UR = "https://api.uptimerobot.com/v2/getMonitors";
export const API = "https://api.example.test";
