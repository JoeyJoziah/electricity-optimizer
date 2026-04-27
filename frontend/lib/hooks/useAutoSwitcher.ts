"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  approveSwitch,
  checkNow,
  getActivity,
  getSettings,
  rollback,
} from "@/lib/api/agent-switcher";
import { getAutoSwitcherActivity } from "@/lib/api/auto-switcher";

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

/**
 * Sidebar-only namespace. The sidebar pendingCount badge polls a
 * lightweight activity endpoint shape and must not collide with the
 * dashboard's richer audit-entry cache.
 */
export const autoSwitcherKeys = {
  all: ["auto-switcher"] as const,
  activity: ["auto-switcher", "activity"] as const,
  pendingCount: ["auto-switcher", "pending-count"] as const,
};

/**
 * Dashboard namespace. Each dashboard sub-component subscribes through
 * one of these keys so a single mutation only invalidates the slice
 * that actually changed server-side.
 */
export const agentSwitcherKeys = {
  all: ["agent-switcher"] as const,
  settings: ["agent-switcher", "settings"] as const,
  activity: ["agent-switcher", "activity"] as const,
  history: ["agent-switcher", "history"] as const,
};

// ---------------------------------------------------------------------------
// Sidebar hooks (existing — unchanged behavior)
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

// ---------------------------------------------------------------------------
// Dashboard hooks (queries)
// ---------------------------------------------------------------------------

/**
 * Fetch the current user's agent settings (enabled, LOA, thresholds).
 * Owned by AgentStatusCard.
 */
export function useAgentSettings() {
  return useQuery({
    queryKey: agentSwitcherKeys.settings,
    queryFn: ({ signal }) => getSettings(signal),
    staleTime: 30_000,
  });
}

/**
 * Fetch the most recent N audit-log activity entries.
 * Shared by AgentStatusCard (lastScan), ProtectedBanner,
 * PendingRecommendations, and ActivityFeed via the React Query cache.
 */
export function useAgentActivity(limit: number = 10) {
  return useQuery({
    queryKey: agentSwitcherKeys.activity,
    queryFn: ({ signal }) => getActivity(limit, signal),
    staleTime: 60_000,
  });
}

// ---------------------------------------------------------------------------
// Dashboard hooks (mutations)
// ---------------------------------------------------------------------------

/**
 * Trigger an on-demand evaluation. The backend writes a new row to
 * switch_audit_log and returns the decision; it does NOT modify
 * agent_settings, so we invalidate only the activity slice.
 */
export function useCheckNow() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => checkNow(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentSwitcherKeys.activity });
    },
  });
}

/**
 * Approve a recommended switch. Creates a switch_executions row and
 * marks the audit entry executed=true, so activity is invalidated.
 */
export function useApproveSwitch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (auditLogId: string) => approveSwitch(auditLogId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentSwitcherKeys.activity });
    },
  });
}

/**
 * Roll back an executed switch. Updates switch_executions and may insert
 * a new audit entry, so activity is invalidated.
 */
export function useRollback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (executionId: string) => rollback(executionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: agentSwitcherKeys.activity });
    },
  });
}
