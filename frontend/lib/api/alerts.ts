/**
 * Alerts API functions
 *
 * CRUD operations for user price-alert configurations and
 * paginated alert trigger history.
 */

import { apiClient } from './client'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Alert {
  id: string
  user_id: string
  region: string
  currency: string
  price_below: number | null
  price_above: number | null
  notify_optimal_windows: boolean
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export interface AlertHistoryItem {
  id: string
  user_id: string
  alert_config_id: string | null
  alert_type: string
  current_price: number
  threshold: number | null
  region: string
  supplier: string | null
  currency: string
  optimal_window_start: string | null
  optimal_window_end: string | null
  estimated_savings: number | null
  triggered_at: string | null
  email_sent: boolean
}

export interface GetAlertsResponse {
  alerts: Alert[]
  total: number
}

export interface GetAlertHistoryResponse {
  items: AlertHistoryItem[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface CreateAlertRequest {
  region: string
  currency?: string
  price_below?: number | null
  price_above?: number | null
  notify_optimal_windows?: boolean
}

export interface UpdateAlertRequest {
  region?: string
  currency?: string
  price_below?: number | null
  price_above?: number | null
  notify_optimal_windows?: boolean
  is_active?: boolean
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * Get all alert configurations for the current user
 */
export async function getAlerts(signal?: AbortSignal): Promise<GetAlertsResponse> {
  return apiClient.get<GetAlertsResponse>('/alerts', undefined, { signal })
}

/**
 * Create a new alert configuration
 */
export async function createAlert(body: CreateAlertRequest): Promise<Alert> {
  return apiClient.post<Alert>('/alerts', body)
}

/**
 * Update an existing alert configuration
 */
export async function updateAlert(
  id: string,
  body: UpdateAlertRequest
): Promise<Alert> {
  return apiClient.put<Alert>(`/alerts/${id}`, body)
}

/**
 * Delete an alert configuration
 */
export async function deleteAlert(
  id: string
): Promise<{ deleted: boolean; alert_id: string }> {
  return apiClient.delete<{ deleted: boolean; alert_id: string }>(
    `/alerts/${id}`
  )
}

/**
 * Get paginated alert trigger history
 */
export async function getAlertHistory(
  page: number = 1,
  pageSize: number = 20,
  signal?: AbortSignal,
): Promise<GetAlertHistoryResponse> {
  return apiClient.get<GetAlertHistoryResponse>('/alerts/history', {
    page: page.toString(),
    page_size: pageSize.toString(),
  }, { signal })
}
