'use client'

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getCurrentPrices, getPriceHistory, getPriceForecast, getOptimalPeriods } from '@/lib/api/prices'

/**
 * Hook for fetching current electricity prices
 */
export function useCurrentPrices(region: string | null) {
  return useQuery({
    queryKey: ['prices', 'current', region],
    queryFn: () => getCurrentPrices(region!),
    enabled: !!region,
    refetchInterval: 60000, // Refetch every minute
    staleTime: 55000, // Stale just before next poll to prevent window-focus gap refetch
  })
}

/**
 * Hook for fetching price history
 */
export function usePriceHistory(region: string | null, hours: number = 24) {
  return useQuery({
    queryKey: ['prices', 'history', region, hours],
    queryFn: () => getPriceHistory(region!, hours),
    enabled: !!region,
    staleTime: 60000, // Consider stale after 1 minute
  })
}

/**
 * Hook for fetching price forecast
 */
export function usePriceForecast(region: string | null, hours: number = 24) {
  return useQuery({
    queryKey: ['prices', 'forecast', region, hours],
    queryFn: () => getPriceForecast(region!, hours),
    enabled: !!region,
    refetchInterval: 300000, // Refetch every 5 minutes
    staleTime: 180000, // Consider stale after 3 minutes
  })
}

/**
 * Hook for fetching optimal periods
 */
export function useOptimalPeriods(region: string | null, hours: number = 24) {
  return useQuery({
    queryKey: ['prices', 'optimal', region, hours],
    queryFn: () => getOptimalPeriods(region!, hours),
    enabled: !!region,
    refetchInterval: 300000,
    staleTime: 180000,
  })
}

/**
 * Hook to manually refresh all price data
 */
export function useRefreshPrices() {
  const queryClient = useQueryClient()

  return () => {
    queryClient.invalidateQueries({ queryKey: ['prices'] })
  }
}
