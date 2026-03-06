import { API_ORIGIN } from '@/lib/config/env'

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
  let url = `${API_ORIGIN}/api/v1/connections/analytics/${path}`
  if (params && Object.keys(params).length > 0) {
    const qs = new URLSearchParams(params).toString()
    url += `?${qs}`
  }
  const res = await fetch(url, { credentials: 'include' })
  if (!res.ok) {
    throw new Error(`Failed to fetch ${path}: ${res.status}`)
  }
  return res.json()
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
