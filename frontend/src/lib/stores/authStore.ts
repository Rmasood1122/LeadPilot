"use client";

/**
 * authStore compat shim — combined build.
 *
 * The M8-C3 admin route group and PlanCard were written against a zustand
 * `useAuthStore` that never existed in the M5 frontend (which uses plain
 * session helpers in lib/api/client). This shim provides the same hook
 * surface — { user, isLoading } — backed by GET /auth/me and a module-level
 * cache, without adding a state-management dependency.
 */

import { useEffect, useState } from "react";
import { api, hasSession } from "@/lib/api/client";

export interface AuthUser {
  id: string;
  email: string;
  plan: string;
  is_admin?: boolean;
}

interface AuthState {
  user: AuthUser | null;
  isLoading: boolean;
}

// Module-level cache shared by every component using the hook,
// so /auth/me is fetched once per page load, not once per component.
let cached: AuthUser | null = null;
let inflight: Promise<AuthUser | null> | null = null;

async function fetchUser(): Promise<AuthUser | null> {
  if (cached) return cached;
  if (!hasSession()) return null;
  if (!inflight) {
    inflight = api<AuthUser>("/auth/me")
      .then((u) => {
        cached = u;
        return u;
      })
      .catch(() => null)
      .finally(() => {
        inflight = null;
      });
  }
  return inflight;
}

/** Call after logout so the next mount re-fetches. */
export function resetAuthStore(): void {
  cached = null;
}

export function useAuthStore(): AuthState {
  const [state, setState] = useState<AuthState>({
    user: cached,
    isLoading: cached === null,
  });

  useEffect(() => {
    let mounted = true;
    if (cached) {
      setState({ user: cached, isLoading: false });
      return;
    }
    fetchUser().then((u) => {
      if (mounted) setState({ user: u, isLoading: false });
    });
    return () => {
      mounted = false;
    };
  }, []);

  return state;
}
