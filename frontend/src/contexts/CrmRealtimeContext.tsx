"use client";

/** M9 real-time: binds the shared SSE client to the React Query cache.
 *
 * Mounted ONCE, in src/app/(app)/crm/layout.tsx, so the connection is opened
 * when the user enters the CRM and closed when they leave it — a user who
 * never opens the CRM never holds a stream, and moving between the dashboard
 * and the grid keeps the same one.
 *
 * WHAT IT DOES WITH AN EVENT
 * Invalidates the affected React Query keys rather than hand-patching row
 * data into the cache. Patching looks cheaper, but the events carry a
 * summary of what changed, not the full row shape each screen renders (the
 * grid row alone joins tags, custom values and a note count). Reconciling a
 * partial payload against five different cached shapes is where subtle
 * "the number is wrong until you refresh" bugs come from. An invalidate
 * costs one request and is always correct.
 *
 * The invalidations are DEBOUNCED. A bulk status change on 200 leads emits
 * 200 events in a few hundred milliseconds; invalidating per event would
 * fire 200 refetches of the same query.
 */

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  getCrmStreamClient,
  type CrmConnectionState,
} from "@/lib/crm/sse-client";
import type { CrmStreamEventName } from "@/lib/api/types";

interface CrmRealtimeValue {
  state: CrmConnectionState;
  /** True while the stream is carrying updates — the UI shows "Live". When
   *  false the React Query poll fallback is doing the work, and the UI says
   *  so rather than pretending. */
  live: boolean;
  /** Timestamp of the last event received, for the "updated Xs ago" label. */
  lastEventAt: number | null;
}

const CrmRealtimeContext = createContext<CrmRealtimeValue>({
  state: "idle",
  live: false,
  lastEventAt: null,
});

/** Coalescing window for cache invalidation. 250ms is below the threshold
 *  where a person perceives lag, and comfortably above the burst width of a
 *  bulk action. */
const INVALIDATE_DEBOUNCE_MS = 250;

/** Which query keys each event type makes stale. */
function keysFor(name: CrmStreamEventName): string[] {
  switch (name) {
    case "lead.status_changed":
      // A status change moves a lead between funnel stages, so it touches
      // every dashboard as well as the grid.
      return ["crm-grid", "crm-pipeline", "crm-leads", "crm-activity", "leads"];
    case "lead.updated":
      return ["crm-grid", "crm-leads", "leads"];
    case "note.created":
      return ["crm-grid", "crm-notes", "crm-activity"];
    case "outcome.created":
      return ["crm-pipeline", "crm-campaigns", "crm-activity"];
    case "activity.created":
      return ["crm-activity"];
    default:
      return [];
  }
}

export function CrmRealtimeProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<CrmConnectionState>("idle");
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);

  const pending = useRef<Set<string>>(new Set());
  const flushTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const client = getCrmStreamClient();

    const flush = () => {
      flushTimer.current = null;
      const keys = Array.from(pending.current);
      pending.current.clear();
      for (const key of keys) {
        // Prefix match: ["crm-grid", {...query}] is invalidated by ["crm-grid"].
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    };

    const offEvent = client.onEvent((name) => {
      const keys = keysFor(name);
      if (keys.length === 0) return;
      for (const key of keys) pending.current.add(key);
      setLastEventAt(Date.now());
      if (flushTimer.current === null) {
        flushTimer.current = setTimeout(flush, INVALIDATE_DEBOUNCE_MS);
      }
    });

    const offState = client.onStateChange(setState);
    setState(client.getState());
    void client.start();

    // Mobile Safari and the Capacitor WebView drop the socket on
    // backgrounding, frequently without firing onerror — so returning to the
    // foreground triggers an immediate reconnect rather than waiting out a
    // backoff that was scheduled before the screen went off.
    const onVisibility = () => {
      if (document.visibilityState === "visible") client.resume();
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      offEvent();
      offState();
      if (flushTimer.current !== null) {
        clearTimeout(flushTimer.current);
        flushTimer.current = null;
      }
      client.stop();
    };
  }, [queryClient]);

  const value = useMemo<CrmRealtimeValue>(
    () => ({ state, live: state === "open", lastEventAt }),
    [state, lastEventAt],
  );

  return (
    <CrmRealtimeContext.Provider value={value}>
      {children}
    </CrmRealtimeContext.Provider>
  );
}

export function useCrmRealtime(): CrmRealtimeValue {
  return useContext(CrmRealtimeContext);
}
