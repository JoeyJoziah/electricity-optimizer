import { apiClient } from './client'

export interface HeatingOilPrice {
  id: string
  state: string
  price_per_gallon: number
  source: string
  period_date: string | null
  fetched_at: string | null
}

export interface HeatingOilPricesResponse {
  prices: HeatingOilPrice[]
  tracked_states: string[]
}

export interface HeatingOilHistoryResponse {
  state: string
  weeks: number
  history: HeatingOilPrice[]
  comparison: HeatingOilComparison | null
}

export interface HeatingOilComparison {
  state: string
  price_per_gallon: number
  national_avg: number | null
  difference_pct: number | null
  estimated_monthly_cost: number
  estimated_annual_cost: number
}

export interface HeatingOilDealer {
  id: string
  name: string
  state: string
  city: string | null
  phone: string | null
  website: string | null
  rating: number | null
}

export interface HeatingOilDealersResponse {
  state: string
  count: number
  dealers: HeatingOilDealer[]
}

export async function getHeatingOilPrices(
  state?: string,
  signal?: AbortSignal,
): Promise<HeatingOilPricesResponse> {
  return apiClient.get<HeatingOilPricesResponse>(
    '/rates/heating-oil',
    state ? { state } : {},
    { signal },
  )
}

export async function getHeatingOilHistory(
  state: string,
  weeks?: number,
  signal?: AbortSignal,
): Promise<HeatingOilHistoryResponse> {
  return apiClient.get<HeatingOilHistoryResponse>(
    '/rates/heating-oil/history',
    { state, ...(weeks ? { weeks } : {}) },
    { signal },
  )
}

export async function getHeatingOilDealers(
  state: string,
  limit?: number,
  signal?: AbortSignal,
): Promise<HeatingOilDealersResponse> {
  return apiClient.get<HeatingOilDealersResponse>(
    '/rates/heating-oil/dealers',
    { state, ...(limit ? { limit } : {}) },
    { signal },
  )
}

export async function getHeatingOilComparison(
  state: string,
  signal?: AbortSignal,
): Promise<HeatingOilComparison> {
  return apiClient.get<HeatingOilComparison>(
    '/rates/heating-oil/compare',
    { state },
    { signal },
  )
}
