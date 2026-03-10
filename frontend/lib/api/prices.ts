/**
 * Price API functions.
 *
 * Response types are sourced from the generated OpenAPI types
 * (types/generated/api.ts) rather than hand-authored interfaces.
 * Use the normalisation helpers in types/api-helpers.ts to convert
 * snake_case API shapes to camelCase before passing to UI components.
 */

import { apiClient } from './client'
import type {
  ApiCurrentPriceResponse,
  ApiPriceHistoryResponse,
  ApiPriceForecastResponse,
  ApiPriceComparisonResponse,
} from '@/types/generated/api'

// ---------------------------------------------------------------------------
// Re-export generated response types so call-sites can import from one place
// ---------------------------------------------------------------------------

export type {
  ApiCurrentPriceResponse,
  ApiPriceHistoryResponse,
  ApiPriceForecastResponse,
  ApiPriceComparisonResponse,
}

// ---------------------------------------------------------------------------
// Request parameter types
// ---------------------------------------------------------------------------

export interface GetCurrentPricesParams {
  region: string
  supplier?: string
  /** Maximum number of prices to return (1–100, default 10) */
  limit?: number
}

export interface GetPriceHistoryParams {
  region: string
  /** Number of days of history (1–365, default 7). Ignored when start_date/end_date provided. */
  days?: number
  supplier?: string
  /** ISO-8601 start date (inclusive) */
  startDate?: string
  /** ISO-8601 end date (inclusive) */
  endDate?: string
  /** 1-based page number (default 1) */
  page?: number
  /** Records per page (1–100, default 24) */
  pageSize?: number
}

export interface GetPriceForecastParams {
  region: string
  /** Forecast horizon in hours (1–168, default 24) */
  hours?: number
  supplier?: string
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

/**
 * GET /prices/current
 *
 * Returns current electricity prices for a region.
 * Response includes `prices` (array) when no supplier filter is given,
 * or `price` (single object) when a supplier is specified.
 */
export async function getCurrentPrices(
  params: GetCurrentPricesParams
): Promise<ApiCurrentPriceResponse> {
  const query: Record<string, string> = { region: params.region }
  if (params.supplier) query.supplier = params.supplier
  if (params.limit !== undefined) query.limit = String(params.limit)

  return apiClient.get<ApiCurrentPriceResponse>('/prices/current', query)
}

/**
 * GET /prices/history
 *
 * Returns paginated historical electricity prices.
 * Backend returns full Price objects with price_per_kwh (Decimal string) and timestamp.
 * Use parseDecimal() from types/api-helpers.ts before arithmetic.
 */
export async function getPriceHistory(
  params: GetPriceHistoryParams
): Promise<ApiPriceHistoryResponse> {
  const query: Record<string, string> = { region: params.region }
  if (params.days !== undefined) query.days = String(params.days)
  if (params.supplier) query.supplier = params.supplier
  if (params.startDate) query.start_date = params.startDate
  if (params.endDate) query.end_date = params.endDate
  if (params.page !== undefined) query.page = String(params.page)
  if (params.pageSize !== undefined) query.page_size = String(params.pageSize)

  return apiClient.get<ApiPriceHistoryResponse>('/prices/history', query)
}

/**
 * GET /prices/forecast  (requires Pro tier)
 *
 * Returns ML-generated price forecast.
 * confidence is a float 0–1.
 */
export async function getPriceForecast(
  params: GetPriceForecastParams
): Promise<ApiPriceForecastResponse> {
  const query: Record<string, string> = { region: params.region }
  if (params.hours !== undefined) query.hours = String(params.hours)
  if (params.supplier) query.supplier = params.supplier

  return apiClient.get<ApiPriceForecastResponse>('/prices/forecast', query)
}

/**
 * GET /prices/compare
 *
 * Compare electricity prices across suppliers in a region.
 * Returns suppliers sorted cheapest-first with summary statistics.
 */
export async function comparePrices(
  region: string
): Promise<ApiPriceComparisonResponse> {
  return apiClient.get<ApiPriceComparisonResponse>('/prices/compare', { region })
}

// ---------------------------------------------------------------------------
// Convenience overloads for call-sites that still pass positional arguments
//
// These are thin wrappers so existing callers don't need to be updated yet.
// New call-sites should prefer the params-object variants above.
// ---------------------------------------------------------------------------

/**
 * @deprecated Use getCurrentPrices({ region }) instead.
 */
export async function getCurrentPricesLegacy(
  region: string
): Promise<ApiCurrentPriceResponse> {
  return getCurrentPrices({ region })
}

/**
 * @deprecated Use getPriceHistory({ region, days }) instead.
 */
export async function getPriceHistoryLegacy(
  region: string,
  days = 7
): Promise<ApiPriceHistoryResponse> {
  return getPriceHistory({ region, days })
}

/**
 * @deprecated Use getPriceForecast({ region, hours }) instead.
 */
export async function getPriceForecastLegacy(
  region: string,
  hours = 24
): Promise<ApiPriceForecastResponse> {
  return getPriceForecast({ region, hours })
}

/**
 * GET /prices/optimal-periods
 *
 * Returns low-cost windows for energy usage in the next N hours.
 * Note: this endpoint is not yet reflected in the generated OpenAPI types
 * because the backend does not declare a formal response_model for it.
 * The inline type below matches the observed response shape.
 */
export async function getOptimalPeriods(
  region: string,
  hours = 24
): Promise<{ periods: Array<{ start: string; end: string; avgPrice: number }> }> {
  return apiClient.get('/prices/optimal-periods', {
    region,
    hours: String(hours),
  })
}
