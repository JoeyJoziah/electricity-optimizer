"use client";

import React, { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Cache policy hierarchy (see also: workers/api-gateway/src/config.ts):
// - Default staleTime: 60s (here). Override per-hook in frontend/lib/hooks/*.ts
// - Price data: 55s-180s staleTime (hooks) + 300s CF Worker TTL + 30s backend tier cache
// - Suppliers: 300s staleTime (hooks) + 3600s CF Worker TTL
// - CCA/reports: 3600s staleTime (hooks) + no CF cache (auth-gated)
// - CF Worker sends Cache-Control: private, max-age=<remaining> on cache hits
// - gcTime: 5min default. Tests override to 0 for isolation.
export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 1 minute
            gcTime: 5 * 60 * 1000, // 5 minutes
            refetchOnWindowFocus: false, // Prevent perceived page refreshes when switching tabs
            // Smart retry strategy:
            // - 4xx (except 408/429): no retry — client/auth problems
            // - 429 rate limited: no retry — apiClient handles global 503 cooldown
            //   to prevent cascade; retrying 429 only makes it worse
            // - 503 unavailable: retry once — the global 503 cooldown in apiClient
            //   already serializes retries with a 3s delay between attempts, so
            //   React Query should retry sparingly to avoid dogpiling
            // - Other 5xx: retry twice (existing behavior)
            retry: (failureCount, error) => {
              const status =
                error &&
                typeof error === "object" &&
                "status" in error &&
                typeof (error as { status: unknown }).status === "number"
                  ? (error as { status: number }).status
                  : 0;
              // No retry for client errors (except timeout/rate-limit handled below)
              if (status >= 400 && status < 500) return false;
              // 503 — let apiClient's cooldown handle it, only 1 React Query retry
              if (status === 503) return failureCount < 1;
              return failureCount < 2;
            },
            retryDelay: (attemptIndex, error) => {
              const status =
                error && typeof error === "object" && "status" in error
                  ? (error as { status: number }).status
                  : 0;
              // Longer delay for 503 — backend needs time to warm up
              if (status === 503) return 3000;
              return Math.min(1000 * 2 ** attemptIndex, 30000);
            },
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}
