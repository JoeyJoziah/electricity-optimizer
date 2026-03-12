import { apiClient } from '../api-client'

export interface PropanePrice {
  id: string
  state: string
  price_per_gallon: number
  source: string
  period_date: string | null
  fetched_at: string | null
}

export interface PropanePricesResponse {
  prices: PropanePrice[]
  tracked_states: string[]
}

export interface PropaneHistoryResponse {
  state: string
  weeks: number
  history: PropanePrice[]
  comparison: PropaneComparison | null
}

export interface PropaneComparison {
  state: string
  price_per_gallon: number
  national_avg: number | null
  difference_pct: number | null
  estimated_monthly_cost: number
  estimated_annual_cost: number
}

export interface PropaneTimingAdvice {
  state: string
  timing: 'good' | 'wait' | 'neutral'
  current_price: number
  avg_price: number
  advice: string
  data_points: number
}

export async function getPropanePrices(
  state?: string,
): Promise<PropanePricesResponse> {
  return apiClient.get<PropanePricesResponse>(
    '/rates/propane',
    state ? { state } : {},
  )
}

export async function getPropaneHistory(
  state: string,
  weeks?: number,
): Promise<PropaneHistoryResponse> {
  return apiClient.get<PropaneHistoryResponse>(
    '/rates/propane/history',
    { state, ...(weeks ? { weeks: String(weeks) } : {}) },
  )
}

export async function getPropaneComparison(
  state: string,
): Promise<PropaneComparison> {
  return apiClient.get<PropaneComparison>(
    '/rates/propane/compare',
    { state },
  )
}

export async function getPropaneTiming(
  state: string,
): Promise<PropaneTimingAdvice> {
  return apiClient.get<PropaneTimingAdvice>(
    '/rates/propane/timing',
    { state },
  )
}
