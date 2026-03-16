import { apiClient, ApiClientError } from '@/lib/api/client'

// ---------------------------------------------------------------------------
// Shared types for ConnectionAnalytics sub-components
// ---------------------------------------------------------------------------

export interface RateComparison {
  user_rate: number
  market_average: number
  delta: number
  percentage_difference: number
  is_above_average: boolean
}

export interface SavingsEstimate {
  estimated_annual_savings_vs_best: number
  estimated_monthly_savings_vs_best: number
  current_annual_cost: number
}

export interface RateHistoryPoint {
  date: string
  rate: number
  supplier: string
}

export interface RateHistory {
  data_points: RateHistoryPoint[]
}

export interface StaleConnection {
  id: string
  supplier_name: string
  last_sync_at: string | null
  days_since_sync: number
}

export interface RateChangeAlert {
  id: string
  supplier_name: string
  old_rate: number
  new_rate: number
  change_percentage: number
  detected_at: string
}

export interface ConnectionHealth {
  stale_connections: StaleConnection[]
  rate_change_alerts: RateChangeAlert[]
}

export type CardLoadingState = 'idle' | 'loading' | 'success' | 'error'

// ---------------------------------------------------------------------------
// Fetch helper
// ---------------------------------------------------------------------------

export async function fetchAnalytics<T>(
  path: string,
  params?: Record<string, string>
): Promise<T> {
  try {
    return await apiClient.get<T>(`/connections/analytics/${path}`, params)
  } catch (err) {
    if (err instanceof ApiClientError && err.status === 403) {
      throw new Error('Upgrade required')
    }
    throw new Error(`Failed to fetch ${path}`)
  }
}

// ---------------------------------------------------------------------------
// Shared utility
// ---------------------------------------------------------------------------

export function formatDate(dateString: string): string {
  try {
    const d = new Date(dateString)
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  } catch {
    return dateString
  }
}
