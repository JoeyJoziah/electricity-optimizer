/**
 * Auto Switcher API functions
 *
 * Fetches agent-switcher activity data for pending recommendation
 * badge counts and activity listing.
 */

import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SwitcherActivity {
  id: string;
  decision: string;
  executed: boolean;
  created_at: string;
  rate_plan_id?: string | null;
  savings_estimate?: number | null;
  region?: string | null;
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Get recent auto-switcher activity (recommendations and executions).
 * Used by the sidebar badge to show pending recommendation count.
 */
export async function getAutoSwitcherActivity(
  limit: number = 10,
  signal?: AbortSignal,
): Promise<SwitcherActivity[]> {
  return apiClient.get<SwitcherActivity[]>(
    "/agent-switcher/activity",
    {
      limit: limit.toString(),
    },
    { signal },
  );
}
