/**
 * Rate Changes API functions
 *
 * Fetch detected rate changes across utility types and
 * manage per-utility alert preferences.
 */

import { apiClient } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RateChange {
  id: string
  utility_type: string
  region: string
  supplier: string
  previous_price: number
  current_price: number
  change_pct: number
  change_direction: 'increase' | 'decrease'
  detected_at: string
  recommendation_supplier: string | null
  recommendation_price: number | null
  recommendation_savings: number | null
}

export interface GetRateChangesResponse {
  changes: RateChange[]
  total: number
}

export interface AlertPreference {
  id: string
  user_id: string
  utility_type: string
  enabled: boolean
  channels: string[]
  cadence: string
  created_at: string
  updated_at: string
}

export interface GetAlertPreferencesResponse {
  preferences: AlertPreference[]
}

export interface UpsertPreferenceRequest {
  utility_type: string
  enabled?: boolean
  channels?: string[]
  cadence?: string
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Get recent rate changes, optionally filtered.
 */
export async function getRateChanges(
  params?: {
    utility_type?: string
    region?: string
    days?: number
    limit?: number
  },
  signal?: AbortSignal,
): Promise<GetRateChangesResponse> {
  const query: Record<string, string> = {}
  if (params?.utility_type) query.utility_type = params.utility_type
  if (params?.region) query.region = params.region
  if (params?.days) query.days = params.days.toString()
  if (params?.limit) query.limit = params.limit.toString()

  return apiClient.get<GetRateChangesResponse>('/rate-changes', query, { signal })
}

/**
 * Get the authenticated user's alert preferences.
 */
export async function getAlertPreferences(signal?: AbortSignal): Promise<GetAlertPreferencesResponse> {
  return apiClient.get<GetAlertPreferencesResponse>('/rate-changes/preferences', undefined, { signal })
}

/**
 * Create or update a per-utility alert preference.
 */
export async function upsertAlertPreference(
  body: UpsertPreferenceRequest
): Promise<AlertPreference> {
  return apiClient.put<AlertPreference>('/rate-changes/preferences', body)
}
