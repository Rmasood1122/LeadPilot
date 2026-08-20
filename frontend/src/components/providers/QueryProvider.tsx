"use client";

/**
 * QueryProvider — real TanStack Query provider.
 *
 * Was a no-op passthrough shim until M8: M5 pages used plain fetch() via
 * lib/api/client so no QueryClient was wired up. M8 added pages that call
 * useQuery() directly (pipeline, campaigns, settings, admin/*), which
 * crashed at runtime with "No QueryClient set, use QueryClientProvider to
 * set one" because this provider never actually provided one.
 */
import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export function QueryProvider({ children }: { children: ReactNode }) {
  // useState ensures one QueryClient per component tree (not per render),
  // and — critically for Next.js App Router — a fresh client per request
  // on the server while staying stable across client re-renders.
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}