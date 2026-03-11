/**
 * Gas Rate API functions.
 *
 * Calls the backend gas rate endpoints under /rates/natural-gas.
 */

import { apiClient } from './client'

// ---------------------------------------------------------------------------
// Response types (match backend response shapes)
// ---------------------------------------------------------------------------

export interface GasPrice {
  id: string
  supplier: string
  price: string // Decimal string ($/therm)
  unit: string
  timestamp: string
  source: string
}

export interface GasRatesResponse {
  region: string
  utility_type: 'natural_gas'
  unit: string
  is_deregulated: boolean
  count: number
  prices: GasPrice[]
}

export interface GasHistoryResponse {
  region: string
  utility_type: 'natural_gas'
  period_days: number
  count: number
  prices: Array<{
    price: string
    timestamp: string
    supplier: string
  }>
}

export interface GasStatsResponse {
  region: string
  utility_type: 'natural_gas'
  unit: string
  avg_price: string | null
  min_price: string | null
  max_price: string | null
  count: number
}

export interface GasDeregulatedState {
  state_code: string
  state_name: string
  puc_name: string | null
  puc_website: string | null
  comparison_tool_url: string | null
}

export interface GasDeregulatedStatesResponse {
  count: number
  states: GasDeregulatedState[]
}

export interface GasSupplier {
  supplier: string
  price: string
  timestamp: string
  source: string
}

export interface GasCompareResponse {
  region: string
  is_deregulated: boolean
  unit?: string
  suppliers: GasSupplier[]
  cheapest: string | null
  message?: string
}

// ---------------------------------------------------------------------------
// Request parameter types
// ---------------------------------------------------------------------------

export interface GetGasRatesParams {
  region: string
  limit?: number
}

export interface GetGasHistoryParams {
  region: string
  days?: number
}

export interface GetGasStatsParams {
  region: string
  days?: number
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export async function getGasRates(
  params: GetGasRatesParams
): Promise<GasRatesResponse> {
  const query: Record<string, string> = { region: params.region }
  if (params.limit !== undefined) query.limit = String(params.limit)
  return apiClient.get<GasRatesResponse>('/rates/natural-gas/', query)
}

export async function getGasHistory(
  params: GetGasHistoryParams
): Promise<GasHistoryResponse> {
  const query: Record<string, string> = { region: params.region }
  if (params.days !== undefined) query.days = String(params.days)
  return apiClient.get<GasHistoryResponse>('/rates/natural-gas/history', query)
}

export async function getGasStats(
  params: GetGasStatsParams
): Promise<GasStatsResponse> {
  const query: Record<string, string> = { region: params.region }
  if (params.days !== undefined) query.days = String(params.days)
  return apiClient.get<GasStatsResponse>('/rates/natural-gas/stats', query)
}

export async function getDeregulatedGasStates(): Promise<GasDeregulatedStatesResponse> {
  return apiClient.get<GasDeregulatedStatesResponse>(
    '/rates/natural-gas/deregulated-states'
  )
}

export async function compareGasSuppliers(
  region: string
): Promise<GasCompareResponse> {
  return apiClient.get<GasCompareResponse>('/rates/natural-gas/compare', {
    region,
  })
}
