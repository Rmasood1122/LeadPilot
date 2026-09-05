/** M9 real-time: ONE EventSource per session, shared by every CRM screen.
 *
 * WHY A MANAGER RATHER THAN A useEffect PER COMPONENT
 * Four dashboard pages and a data grid all want the same events. An
 * EventSource per component means five connections per user, five Redis
 * subscriptions on the server, and five copies of every event arriving in
 * the same tick — each triggering its own React Query cache write. This
 * class owns exactly one connection and fans out to subscribers in-process.
 *
 * WHY IT IS A PLAIN CLASS AND NOT A HOOK
 * The connection has to survive a component unmounting (navigating from the
 * dashboard to the grid must not drop and re-establish it) and it has to be
 * testable without React. The React binding is a thin context in
 * src/contexts/CrmRealtimeContext.tsx.
 *
 * RECONNECTION IS OURS, NOT THE BROWSER'S
 * EventSource reconnects on its own, but it re-requests the SAME URL — and
 * our URL carries a single-use ticket that expired the moment it was
 * redeemed. So the browser's automatic retry can only ever produce a 401
 * loop. `connect()` therefore closes the source on error and schedules its
 * own retry, which mints a fresh ticket first.
 */

import { BASE } from "@/lib/api/client";
import { createStreamTicket } from "@/lib/api/crm";
import type { CrmStreamEventName } from "@/lib/api/types";

export type CrmEventHandler = (name: CrmStreamEventName, data: unknown) => void;

export type CrmConnectionState =
  | "idle"
  | "connecting"
  | "open"
  /** Retrying with backoff — the poll fallback is carrying the UI. */
  | "reconnecting"
  /** Given up (or the server said real-time is off). Polling only. */
  | "offline";

export type StateHandler = (state: CrmConnectionState) => void;

/** Backoff schedule in ms, then capped at the last value.
 *
 *  Starts at 1s so a blip is invisible, ends at 30s so a backgrounded phone
 *  that lost its radio for an hour is not making 3,600 requests. Capped
 *  rather than unbounded because the user WILL come back to the tab, and an
 *  exponential that has climbed to twenty minutes would leave them staring
 *  at stale data long after the network returned. */
const BACKOFF_MS = [1_000, 2_000, 5_000, 10_000, 30_000];

/** Give up after this many consecutive failures and stay on polling until
 *  something (a visibility change, a manual retry) says otherwise. */
const MAX_ATTEMPTS = 12;

export class CrmStreamClient {
  private source: EventSource | null = null;
  private handlers = new Set<CrmEventHandler>();
  private stateHandlers = new Set<StateHandler>();
  private attempt = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private state: CrmConnectionState = "idle";
  private stopped = true;
  /** Guards against two connect() calls racing (a re-subscribe landing while
   *  a retry timer is already in flight). */
  private connecting = false;

  getState(): CrmConnectionState {
    return this.state;
  }

  onEvent(handler: CrmEventHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  onStateChange(handler: StateHandler): () => void {
    this.stateHandlers.add(handler);
    return () => {
      this.stateHandlers.delete(handler);
    };
  }

  private setState(next: CrmConnectionState) {
    if (this.state === next) return;
    this.state = next;
    for (const handler of this.stateHandlers) handler(next);
  }

  private emit(name: CrmStreamEventName, raw: string) {
    let data: unknown = null;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      // A malformed frame is not worth tearing the connection down for; the
      // next one will very likely be fine, and the poll covers the gap.
      return;
    }
    for (const handler of this.handlers) handler(name, data);
  }

  /** Open the stream. Safe to call repeatedly — a second call while already
   *  open or connecting is a no-op. */
  async start(): Promise<void> {
    this.stopped = false;
    if (this.source || this.connecting) return;
    await this.connect();
  }

  private async connect(): Promise<void> {
    if (this.stopped || this.connecting) return;
    this.connecting = true;
    this.setState(this.attempt === 0 ? "connecting" : "reconnecting");

    let ticket: string;
    try {
      ticket = (await createStreamTicket()).ticket;
    } catch (err) {
      this.connecting = false;
      // 503 means the server has real-time switched off (the
      // CRM_STREAM_MAX_SECONDS kill switch, or Redis is gone). Retrying that
      // on a backoff loop is pointless noise — polling is the answer, and
      // the next mount or visibility change will try again.
      const status = (err as { status?: number })?.status;
      if (status === 503) {
        this.setState("offline");
        return;
      }
      this.scheduleRetry();
      return;
    }

    if (this.stopped) {
      this.connecting = false;
      return;
    }

    const source = new EventSource(
      `${BASE}/crm/stream?ticket=${encodeURIComponent(ticket)}`,
    );
    this.source = source;
    this.connecting = false;

    const named: CrmStreamEventName[] = [
      "ready",
      "reconnect",
      "lead.updated",
      "lead.status_changed",
      "note.created",
      "outcome.created",
      "activity.created",
    ];

    for (const name of named) {
      source.addEventListener(name, (event) => {
        if (name === "ready") {
          // Only now is the connection genuinely usable. Resetting the
          // attempt counter HERE rather than on open means a server that
          // accepts the socket and immediately drops it still backs off,
          // instead of hammering it at 1s forever.
          this.attempt = 0;
          this.setState("open");
          return;
        }
        if (name === "reconnect") {
          // The server hit its per-connection cap. This is not a failure, so
          // it reconnects immediately rather than backing off.
          this.cycle();
          return;
        }
        this.emit(name, (event as MessageEvent).data);
      });
    }

    source.onerror = () => {
      // EventSource would retry this URL itself, but the ticket in it is
      // already spent — so close it and run our own retry, which mints a new
      // one.
      source.close();
      if (this.source === source) this.source = null;
      this.scheduleRetry();
    };
  }

  /** Close and immediately reopen — used for the server's `reconnect` notice,
   *  which is a planned cycle rather than a fault. */
  private cycle() {
    if (this.source) {
      this.source.close();
      this.source = null;
    }
    this.attempt = 0;
    void this.connect();
  }

  private scheduleRetry() {
    if (this.stopped) return;
    if (this.attempt >= MAX_ATTEMPTS) {
      this.setState("offline");
      return;
    }
    const delay = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)];
    this.attempt += 1;
    this.setState("reconnecting");
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.connect();
    }, delay);
  }

  /** Called when the tab becomes visible again.
   *
   *  Mobile browsers (and the Capacitor WebView this app also ships as)
   *  suspend timers and kill sockets on backgrounding, often without firing
   *  an error the page can see. So coming back to the foreground is treated
   *  as "assume the stream is dead, and get one immediately" rather than
   *  waiting out whatever backoff was in flight when the screen went off. */
  resume(): void {
    if (this.stopped) return;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.attempt = 0;
    if (this.source) {
      this.source.close();
      this.source = null;
    }
    void this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    if (this.source) {
      this.source.close();
      this.source = null;
    }
    this.setState("idle");
    this.attempt = 0;
  }
}

/** Process-wide singleton.
 *
 *  Module scope, not React state: navigating between /crm/dashboard and
 *  /crm/table must not drop and re-establish the connection, and React
 *  StrictMode double-mounts every effect in development — which with a
 *  per-component EventSource would open two. */
let singleton: CrmStreamClient | null = null;

export function getCrmStreamClient(): CrmStreamClient {
  if (!singleton) singleton = new CrmStreamClient();
  return singleton;
}

/** Test seam: drop the singleton so each test starts clean. */
export function resetCrmStreamClient(): void {
  singleton?.stop();
  singleton = null;
}
