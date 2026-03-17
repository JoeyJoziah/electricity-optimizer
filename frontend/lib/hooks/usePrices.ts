'use client'

import { useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getCurrentPrices,
  getPriceHistory,
  getPriceForecast,
  getOptimalPeriods,
} from '@/lib/api/prices'

/**
 * Hook for fetching current electricity prices.
 * Returns ApiCurrentPriceResponse — use normalisePriceResponse() from
 * types/api-helpers.ts to convert to camelCase for UI components.
 */
export function useCurrentPrices(region: string | null | undefined) {
  return useQuery({
    queryKey: ['prices', 'current', region],
    queryFn: ({ signal }) => getCurrentPrices({ region: region! }, signal),
    enabled: !!region,
    refetchInterval: 60000, // Refetch every minute
    staleTime: 55000, // Stale just before next poll to prevent window-focus gap refetch
  })
}

/**
 * Hook for fetching price history.
 * Returns ApiPriceHistoryResponse — prices[].price_per_kwh is a Decimal string.
 * Use parseDecimal() from types/api-helpers.ts before arithmetic.
 */
export function usePriceHistory(region: string | null | undefined, hours: number = 24) {
  // The backend uses `days` not `hours`; convert for the params object
  const days = Math.max(1, Math.ceil(hours / 24))
  return useQuery({
    queryKey: ['prices', 'history', region, days],
    queryFn: ({ signal }) => getPriceHistory({ region: region!, days }, signal),
    enabled: !!region,
    staleTime: 60000, // Consider stale after 1 minute
  })
}

/**
 * Hook for fetching price forecast (requires Pro tier).
 * Returns ApiPriceForecastResponse — forecast.prices[].price_per_kwh is a Decimal string.
 */
export function usePriceForecast(region: string | null | undefined, hours: number = 24) {
  return useQuery({
    queryKey: ['prices', 'forecast', region, hours],
    queryFn: ({ signal }) => getPriceForecast({ region: region!, hours }, signal),
    enabled: !!region,
    refetchInterval: 300000, // Refetch every 5 minutes
    staleTime: 180000, // Consider stale after 3 minutes
  })
}

/**
 * Hook for fetching optimal usage periods.
 */
export function useOptimalPeriods(region: string | null | undefined, hours: number = 24) {
  return useQuery({
    queryKey: ['prices', 'optimal', region, hours],
    queryFn: ({ signal }) => getOptimalPeriods(region!, hours, signal),
    enabled: !!region,
    refetchInterval: 300000,
    staleTime: 180000,
  })
}

/**
 * Hook to manually refresh all price data.
 * The returned callback is memoised with useCallback so consumers do not
 * re-render just because the hook owner re-renders.
 */
export function useRefreshPrices() {
  const queryClient = useQueryClient()

  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['prices'] })
  }, [queryClient])
}
