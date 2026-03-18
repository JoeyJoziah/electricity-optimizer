"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";

export interface SavingsSummary {
  total: number;
  weekly: number;
  monthly: number;
  streak_days: number;
  currency: string;
}

/**
 * Hook for fetching the authenticated user's savings summary.
 * Returns total/weekly/monthly savings and streak info.
 * Gracefully returns undefined when not authenticated (401).
 *
 * @param enabled - Optional gate; defaults to true. Pass false to defer the
 *   query until upstream data is ready (waterfall staggering).
 */
export function useSavingsSummary(enabled: boolean = true) {
  return useQuery<SavingsSummary>({
    queryKey: ["savings", "summary"],
    queryFn: async ({ signal }) => {
      return apiClient.get<SavingsSummary>("/savings/summary", undefined, {
        signal,
      });
    },
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 1,
  });
}
