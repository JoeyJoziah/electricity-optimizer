"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getNotifications,
  getNotificationCount,
  markNotificationRead,
  markAllRead,
} from "@/lib/api/notifications";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

export const notificationKeys = {
  all: ["notifications"] as const,
  count: ["notifications", "count"] as const,
};

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

/**
 * Fetch the full list of unread notifications.
 * Used when the notification panel is open.
 * staleTime: 30s — avoids redundant refetches within the same panel session.
 */
export function useNotifications() {
  return useQuery({
    queryKey: notificationKeys.all,
    queryFn: ({ signal }) => getNotifications(signal),
    staleTime: 30_000,
  });
}

/**
 * Poll the unread notification count every 120 seconds.
 * Used to keep the bell badge current without fetching the full list.
 *
 * Interval rationale:
 * - 30s was unnecessarily aggressive for a badge counter — notifications
 *   arrive infrequently and users tolerate a couple of minutes of lag.
 * - 120s reduces API calls by 4x while remaining responsive enough for
 *   in-session alerts.
 * - refetchOnWindowFocus: true provides immediate refresh when the user
 *   returns to the tab after being away, which is when fresh data matters
 *   most (covers the "missed notification while tab was hidden" case).
 * - refetchIntervalInBackground: false pauses polling while the tab is
 *   hidden, so the effective poll rate is even lower in practice.
 */
export function useNotificationCount() {
  return useQuery({
    queryKey: notificationKeys.count,
    queryFn: ({ signal }) => getNotificationCount(signal),
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: 60_000,
  });
}

/**
 * Mutation to mark a single notification as read.
 * On success, invalidates both the list and the count queries.
 */
export function useMarkRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.all });
      queryClient.invalidateQueries({ queryKey: notificationKeys.count });
    },
  });
}

/**
 * Mutation to mark all unread notifications as read.
 * Fetches the current list internally and marks each one.
 * On success, invalidates both the list and the count queries.
 */
export function useMarkAllRead() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => markAllRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: notificationKeys.all });
      queryClient.invalidateQueries({ queryKey: notificationKeys.count });
    },
  });
}
