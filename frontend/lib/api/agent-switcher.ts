/**
 * Auto Rate Switcher API functions
 *
 * Manage agent-switcher settings, LOA (Letter of Authorization),
 * switch history/activity, and trigger on-demand evaluations.
 */

import { apiClient } from "./client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AgentSettings {
  enabled: boolean;
  savings_threshold_pct: number;
  savings_threshold_min: number;
  cooldown_days: number;
  paused_until: string | null;
  loa_signed: boolean;
  loa_revoked: boolean;
  created_at: string;
  updated_at: string;
}

export interface AgentSettingsUpdate {
  enabled?: boolean;
  savings_threshold_pct?: number;
  savings_threshold_min?: number;
  cooldown_days?: number;
  paused_until?: string | null;
}

export interface SwitchAuditEntry {
  id: string;
  trigger_type: string;
  decision: string;
  reason: string;
  current_plan_name: string | null;
  proposed_plan_name: string | null;
  savings_monthly: number | null;
  savings_annual: number | null;
  etf_cost: number;
  net_savings_year1: number | null;
  confidence_score: number | null;
  tier: string;
  executed: boolean;
  created_at: string;
}

export interface SwitchExecution {
  id: string;
  status: string;
  enrollment_id: string | null;
  old_plan_name: string | null;
  new_plan_name: string | null;
  initiated_at: string | null;
  confirmed_at: string | null;
  enacted_at: string | null;
  rescission_ends: string | null;
  failure_reason: string | null;
  created_at: string;
}

export interface PlanDetails {
  plan_id: string;
  plan_name: string;
  provider_name: string;
  rate_kwh: number;
  fixed_charge: number;
  term_months: number | null;
  etf_amount: number;
}

export interface SwitchDecision {
  action: "switch" | "recommend" | "hold" | "monitor";
  reason: string;
  current_plan: PlanDetails | null;
  proposed_plan: PlanDetails | null;
  projected_savings_monthly: number;
  projected_savings_annual: number;
  etf_cost: number;
  net_savings_year1: number;
  confidence: number;
  contract_expiring_soon: boolean;
  data_source: string;
}

export interface LOAResponse {
  signed_at?: string;
  revoked_at?: string;
  message: string;
}

export interface RollbackResponse {
  status: string;
  message: string;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

/**
 * Get the current user's auto-switcher agent settings
 */
export async function getSettings(
  signal?: AbortSignal,
): Promise<AgentSettings> {
  return apiClient.get<AgentSettings>("/agent-switcher/settings", undefined, {
    signal,
  });
}

/**
 * Update the current user's auto-switcher agent settings
 */
export async function updateSettings(
  settings: AgentSettingsUpdate,
): Promise<AgentSettings> {
  return apiClient.put<AgentSettings>("/agent-switcher/settings", settings);
}

// ---------------------------------------------------------------------------
// Letter of Authorization (LOA)
// ---------------------------------------------------------------------------

/**
 * Sign the LOA granting the agent permission to execute switches
 */
export async function signLOA(): Promise<LOAResponse> {
  return apiClient.post<LOAResponse>("/agent-switcher/loa/sign");
}

/**
 * Revoke a previously signed LOA, disabling automatic execution
 */
export async function revokeLOA(): Promise<LOAResponse> {
  return apiClient.post<LOAResponse>("/agent-switcher/loa/revoke");
}

// ---------------------------------------------------------------------------
// History & Activity
// ---------------------------------------------------------------------------

/**
 * Get paginated switch audit history for the current user
 */
export async function getHistory(
  limit: number = 20,
  offset: number = 0,
  signal?: AbortSignal,
): Promise<SwitchAuditEntry[]> {
  const res = await apiClient.get<{
    history: SwitchAuditEntry[];
    total: number;
  }>(
    "/agent-switcher/history",
    {
      limit,
      offset,
    },
    { signal },
  );
  return res.history ?? [];
}

/**
 * Get recent switch activity (convenience endpoint, most recent first)
 */
export async function getActivity(
  limit: number = 10,
  signal?: AbortSignal,
): Promise<SwitchAuditEntry[]> {
  const res = await apiClient.get<{
    activity: SwitchAuditEntry[];
    total: number;
  }>(
    "/agent-switcher/activity",
    {
      limit,
    },
    { signal },
  );
  return res.activity ?? [];
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------

/**
 * Trigger an on-demand rate evaluation and get a switch decision
 */
export async function checkNow(signal?: AbortSignal): Promise<SwitchDecision> {
  return apiClient.post<SwitchDecision>("/agent-switcher/check", undefined, {
    signal,
  });
}

/**
 * Roll back a previously executed switch
 */
export async function rollback(executionId: string): Promise<RollbackResponse> {
  return apiClient.post<RollbackResponse>(
    `/agent-switcher/executions/${executionId}/rollback`,
  );
}

/**
 * Approve a recommended switch for execution
 */
export async function approveSwitch(
  auditLogId: string,
): Promise<SwitchExecution> {
  return apiClient.post<SwitchExecution>(
    `/agent-switcher/audit/${auditLogId}/approve`,
  );
}
