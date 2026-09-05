/** M9 SSE client — connection lifecycle, backoff, and the ticket handshake.
 *
 * jsdom has no EventSource, so one is faked. That is not a limitation here:
 * the things worth testing are OURS — that a spent ticket is never reused,
 * that a failure backs off instead of hammering, that the server's planned
 * "reconnect" is treated differently from a fault, and that a 503 stops
 * retrying rather than looping. None of those are browser behaviour.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CrmStreamClient,
  getCrmStreamClient,
  resetCrmStreamClient,
} from "@/lib/crm/sse-client";

// --------------------------------------------------------------------------
// A minimal EventSource stand-in
// --------------------------------------------------------------------------

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, ((event: MessageEvent) => void)[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, handler: (event: MessageEvent) => void) {
    const existing = this.listeners.get(name) ?? [];
    this.listeners.set(name, [...existing, handler]);
  }

  close() {
    this.closed = true;
  }

  /** Deliver a server event to whatever registered for it. */
  emit(name: string, data: unknown) {
    for (const handler of this.listeners.get(name) ?? []) {
      handler({ data: JSON.stringify(data) } as MessageEvent);
    }
  }

  fail() {
    this.onerror?.();
  }

  static latest(): FakeEventSource {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1];
  }

  static reset() {
    FakeEventSource.instances = [];
  }
}

const ticket = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/crm", () => ({
  createStreamTicket: ticket,
}));

vi.mock("@/lib/api/client", () => ({
  BASE: "http://api.test",
}));

/** Let the pending ticket promise settle before asserting on the socket. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

beforeEach(() => {
  FakeEventSource.reset();
  ticket.mockReset();
  ticket.mockResolvedValue({ ticket: "tkt-1", expires_in: 60 });
  (globalThis as unknown as { EventSource: unknown }).EventSource = FakeEventSource;
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  resetCrmStreamClient();
});

describe("connecting", () => {
  it("mints a ticket and puts it in the URL", async () => {
    const client = new CrmStreamClient();
    await client.start();
    await settle();

    expect(ticket).toHaveBeenCalledTimes(1);
    expect(FakeEventSource.latest().url).toBe(
      "http://api.test/crm/stream?ticket=tkt-1",
    );
    client.stop();
  });

  it("never puts an access token in the URL", async () => {
    // The reason the ticket exists. EventSource cannot set headers, so the
    // credential travels in the URL — and it must not be an hour-valid JWT
    // that lands in the access log and the browser history.
    const client = new CrmStreamClient();
    await client.start();
    await settle();
    expect(FakeEventSource.latest().url).not.toMatch(/eyJ/); // a JWT prefix
    client.stop();
  });

  it("reports open only once the server says ready", async () => {
    // A server that accepts the socket and immediately drops it must not be
    // reported as a working connection.
    const client = new CrmStreamClient();
    const states: string[] = [];
    client.onStateChange((state) => states.push(state));

    await client.start();
    await settle();
    expect(client.getState()).toBe("connecting");

    FakeEventSource.latest().emit("ready", { user_id: "u1" });
    expect(client.getState()).toBe("open");
    expect(states).toContain("open");
    client.stop();
  });

  it("start() is idempotent — a second call opens no second socket", async () => {
    const client = new CrmStreamClient();
    await client.start();
    await settle();
    await client.start();
    await settle();
    expect(FakeEventSource.instances).toHaveLength(1);
    client.stop();
  });
});

describe("events", () => {
  it("parses and fans out to every subscriber", async () => {
    const client = new CrmStreamClient();
    const first = vi.fn();
    const second = vi.fn();
    client.onEvent(first);
    client.onEvent(second);

    await client.start();
    await settle();
    FakeEventSource.latest().emit("lead.status_changed", {
      lead_id: "l1",
      to: "flagged",
    });

    expect(first).toHaveBeenCalledWith("lead.status_changed", {
      lead_id: "l1",
      to: "flagged",
    });
    expect(second).toHaveBeenCalledTimes(1);
    client.stop();
  });

  it("ignores a malformed frame rather than tearing the connection down", async () => {
    const client = new CrmStreamClient();
    const handler = vi.fn();
    client.onEvent(handler);
    await client.start();
    await settle();

    const source = FakeEventSource.latest();
    // Deliver raw, unparseable text.
    source.addEventListener("noop", () => undefined);
    const listeners = (source as unknown as {
      listeners: Map<string, ((event: MessageEvent) => void)[]>;
    }).listeners;
    listeners.get("note.created")?.[0]?.({ data: "{not json" } as MessageEvent);

    expect(handler).not.toHaveBeenCalled();
    expect(source.closed).toBe(false);
    client.stop();
  });

  it("unsubscribing stops delivery", async () => {
    const client = new CrmStreamClient();
    const handler = vi.fn();
    const off = client.onEvent(handler);
    await client.start();
    await settle();
    off();
    FakeEventSource.latest().emit("note.created", { note_id: "n1" });
    expect(handler).not.toHaveBeenCalled();
    client.stop();
  });
});

describe("reconnection", () => {
  it("closes the socket on error and retries with a NEW ticket", async () => {
    // The browser would retry the same URL by itself — but that URL carries a
    // single-use ticket that is already spent, so its retry can only ever
    // produce a 401 loop.
    const client = new CrmStreamClient();
    await client.start();
    await settle();

    ticket.mockResolvedValue({ ticket: "tkt-2", expires_in: 60 });
    const first = FakeEventSource.latest();
    first.fail();

    expect(first.closed).toBe(true);
    expect(client.getState()).toBe("reconnecting");

    await vi.advanceTimersByTimeAsync(1100);
    await settle();

    expect(FakeEventSource.instances).toHaveLength(2);
    expect(FakeEventSource.latest().url).toContain("tkt-2");
    client.stop();
  });

  it("backs off — the second retry waits longer than the first", async () => {
    const client = new CrmStreamClient();
    await client.start();
    await settle();

    FakeEventSource.latest().fail();
    await vi.advanceTimersByTimeAsync(1100);
    await settle();
    expect(FakeEventSource.instances).toHaveLength(2);

    FakeEventSource.latest().fail();
    // Still inside the second (2s) delay: nothing new yet.
    await vi.advanceTimersByTimeAsync(1100);
    await settle();
    expect(FakeEventSource.instances).toHaveLength(2);

    await vi.advanceTimersByTimeAsync(1100);
    await settle();
    expect(FakeEventSource.instances).toHaveLength(3);
    client.stop();
  });

  it("resets the backoff after a successful ready", async () => {
    const client = new CrmStreamClient();
    await client.start();
    await settle();

    FakeEventSource.latest().fail();
    await vi.advanceTimersByTimeAsync(1100);
    await settle();
    FakeEventSource.latest().emit("ready", { user_id: "u1" });

    // A later failure starts from the shortest delay again, so one blip an
    // hour never accumulates into a half-minute stall.
    FakeEventSource.latest().fail();
    await vi.advanceTimersByTimeAsync(1100);
    await settle();
    expect(FakeEventSource.instances).toHaveLength(3);
    client.stop();
  });

  it("treats the server's reconnect notice as planned, not as a fault", async () => {
    // It fires when the connection hits its per-connection cap; the stream
    // was working. Backing off there would add a needless gap.
    const client = new CrmStreamClient();
    await client.start();
    await settle();
    FakeEventSource.latest().emit("ready", { user_id: "u1" });

    FakeEventSource.latest().emit("reconnect", {});
    await settle();

    expect(FakeEventSource.instances).toHaveLength(2);
    expect(client.getState()).not.toBe("offline");
    client.stop();
  });

  it("stops retrying when the server says real-time is off", async () => {
    // 503 is the CRM_STREAM_MAX_SECONDS kill switch (or Redis gone).
    // Hammering it on a backoff loop is pointless noise — polling is the
    // answer, and the UI says "Polling".
    ticket.mockRejectedValue(Object.assign(new Error("unavailable"), { status: 503 }));

    const client = new CrmStreamClient();
    await client.start();
    await settle();

    expect(client.getState()).toBe("offline");
    expect(FakeEventSource.instances).toHaveLength(0);

    await vi.advanceTimersByTimeAsync(60_000);
    expect(ticket).toHaveBeenCalledTimes(1);
    client.stop();
  });

  it("retries a transient ticket failure", async () => {
    ticket.mockRejectedValueOnce(Object.assign(new Error("boom"), { status: 500 }));
    ticket.mockResolvedValue({ ticket: "tkt-9", expires_in: 60 });

    const client = new CrmStreamClient();
    await client.start();
    await settle();
    expect(client.getState()).toBe("reconnecting");

    await vi.advanceTimersByTimeAsync(1100);
    await settle();
    expect(FakeEventSource.latest().url).toContain("tkt-9");
    client.stop();
  });

  it("resume() reconnects immediately instead of waiting out the backoff", async () => {
    // Mobile Safari and the Capacitor WebView kill the socket on
    // backgrounding, often silently. Coming back to the foreground should not
    // mean staring at stale data for the remainder of a 30-second delay.
    const client = new CrmStreamClient();
    await client.start();
    await settle();

    FakeEventSource.latest().fail();
    await vi.advanceTimersByTimeAsync(1100);
    await settle();
    FakeEventSource.latest().fail();
    expect(client.getState()).toBe("reconnecting");

    client.resume();
    await settle();

    expect(FakeEventSource.instances).toHaveLength(3);
    client.stop();
  });

  it("stop() closes the socket and cancels a pending retry", async () => {
    const client = new CrmStreamClient();
    await client.start();
    await settle();

    const source = FakeEventSource.latest();
    source.fail();
    client.stop();

    await vi.advanceTimersByTimeAsync(60_000);
    await settle();

    expect(source.closed).toBe(true);
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(client.getState()).toBe("idle");
  });
});

describe("the shared singleton", () => {
  it("hands every caller the same client", () => {
    // One EventSource per session is the requirement. Four dashboard pages
    // and a grid each opening their own would be five connections and five
    // Redis subscriptions per user.
    expect(getCrmStreamClient()).toBe(getCrmStreamClient());
  });

  it("resets cleanly between sessions", () => {
    const first = getCrmStreamClient();
    resetCrmStreamClient();
    expect(getCrmStreamClient()).not.toBe(first);
  });
});
