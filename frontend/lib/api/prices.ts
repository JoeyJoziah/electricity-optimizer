/**
 * Price API functions
 */

import { apiClient } from './client'
import type { CurrentPrice, PriceDataPoint, PriceForecast } from '@/types'

export interface GetCurrentPricesResponse {
  prices: CurrentPrice[]
}

export interface GetPriceHistoryResponse {
  prices: PriceDataPoint[]
}

export interface GetPriceForecastResponse {
  forecast: PriceForecast[]
}

/**
 * Get current electricity prices for a region
 */
export async function getCurrentPrices(
  region: string = 'us_ct'
): Promise<GetCurrentPricesResponse> {
  return apiClient.get<GetCurrentPricesResponse>('/prices/current', { region })
}

/**
 * Get historical price data
 */
export async function getPriceHistory(
  region: string = 'us_ct',
  hours: number = 24
): Promise<GetPriceHistoryResponse> {
  return apiClient.get<GetPriceHistoryResponse>('/prices/history', {
    region,
    hours: hours.toString(),
  })
}

/**
 * Get price forecast for the next N hours
 */
export async function getPriceForecast(
  region: string = 'us_ct',
  hours: number = 24
): Promise<GetPriceForecastResponse> {
  return apiClient.get<GetPriceForecastResponse>('/prices/forecast', {
    region,
    hours: hours.toString(),
  })
}

/**
 * Get optimal time periods for energy usage
 */
export async function getOptimalPeriods(
  region: string = 'us_ct',
  hours: number = 24
): Promise<{ periods: { start: string; end: string; avgPrice: number }[] }> {
  return apiClient.get('/prices/optimal-periods', {
    region,
    hours: hours.toString(),
  })
}
