import { apiClient, ApiClientError } from "@/lib/api/client";

// ---------------------------------------------------------------------------
// Shared types for ConnectionAnalytics sub-components
// ---------------------------------------------------------------------------

// The analytics endpoints return a `{ has_data: false, message }` sentinel when
// the user has a connection but no extracted rate yet. Numeric fields are absent
// in that case, so they are optional and MUST be guarded behind `has_data`.
export interface RateComparison {
  has_data?: boolean;
  message?: string;
  user_rate: number;
  market_average: number;
  delta: number;
  percentage_difference: number;
  is_above_average: boolean;
}

export interface SavingsEstimate {
  has_data?: boolean;
  message?: string;
  estimated_annual_savings_vs_best: number;
  estimated_monthly_savings_vs_best: number;
  current_annual_cost: number;
}

export interface RateHistoryPoint {
  date: string;
  rate: number;
  supplier: string;
}

export interface RateHistory {
  data_points: RateHistoryPoint[];
}

// Field names mirror the backend exactly (connection_analytics_service.py →
// check_stale_connections / detect_rate_changes; router passes the dict through raw).
export interface StaleConnection {
  connection_id: string;
  connection_type?: string | null;
  label: string | null;
  email_provider: string | null;
  last_scan_at: string | null;
  days_since_sync: number | null;
}

export interface RateChangeAlert {
  connection_id: string;
  connection_label: string | null;
  supplier: string | null;
  previous_rate: number;
  current_rate: number;
  change_percentage: number;
  direction: "increase" | "decrease";
  detected_at: string;
}

export interface ConnectionHealth {
  stale_connections: StaleConnection[];
  rate_change_alerts: RateChangeAlert[];
}

export type CardLoadingState = "idle" | "loading" | "success" | "error";

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

export async function fetchAnalytics<T>(
  path: string,
  params?: Record<string, string>,
): Promise<T> {
  try {
    return await apiClient.get<T>(`/connections/analytics/${path}`, params);
  } catch (err) {
    if (err instanceof ApiClientError && err.status === 403) {
      throw new Error("Upgrade required");
    }
    throw new Error(`Failed to fetch ${path}`);
  }
}

// ---------------------------------------------------------------------------
// Shared utility
// ---------------------------------------------------------------------------

export function formatDate(dateString: string): string {
  try {
    const d = new Date(dateString);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return dateString;
  }
}
