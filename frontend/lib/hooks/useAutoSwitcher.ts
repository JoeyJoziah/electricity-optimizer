"use client";

import { useQuery } from "@tanstack/react-query";
import { getAutoSwitcherActivity } from "@/lib/api/auto-switcher";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const autoSwitcherKeys = {
  all: ["auto-switcher"] as const,
  activity: ["auto-switcher", "activity"] as const,
  pendingCount: ["auto-switcher", "pending-count"] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

/**
 * Fetch recent auto-switcher activity (up to 10 items).
 * Used on the Auto Switcher page for the activity feed.
 */
export function useAutoSwitcherActivity() {
  return useQuery({
    queryKey: autoSwitcherKeys.activity,
    queryFn: ({ signal }) => getAutoSwitcherActivity(10, signal),
    staleTime: 60_000, // 1 minute
  });
}

/**
 * Derive the count of pending (unexecuted) recommendations from activity data.
 * Used by the sidebar badge to show actionable item count.
 *
 * Poll interval: 120s (same cadence as notification count) to avoid
 * unnecessary API calls while keeping the badge reasonably fresh.
 * refetchOnWindowFocus ensures immediate update when the user returns.
 */
export function useAutoSwitcherPendingCount() {
  return useQuery({
    queryKey: autoSwitcherKeys.pendingCount,
    queryFn: async ({ signal }) => {
      const activity = await getAutoSwitcherActivity(10, signal);
      return activity.filter((a) => a.decision === "recommend" && !a.executed)
        .length;
    },
    staleTime: 60_000,
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    retry: false,
  });
}
