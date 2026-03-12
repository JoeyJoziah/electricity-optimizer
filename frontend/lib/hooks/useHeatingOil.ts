import { useQuery } from '@tanstack/react-query'
import {
  getHeatingOilPrices,
  getHeatingOilHistory,
  getHeatingOilDealers,
  getHeatingOilComparison,
} from '../api/heating-oil'

export function useHeatingOilPrices(state?: string) {
  return useQuery({
    queryKey: ['heating-oil', 'prices', state],
    queryFn: () => getHeatingOilPrices(state),
    staleTime: 1000 * 60 * 60, // 1 hour
  })
}

export function useHeatingOilHistory(state?: string, weeks?: number) {
  return useQuery({
    queryKey: ['heating-oil', 'history', state, weeks],
    queryFn: () => getHeatingOilHistory(state!, weeks),
    enabled: !!state,
    staleTime: 1000 * 60 * 60,
  })
}

export function useHeatingOilDealers(state?: string) {
  return useQuery({
    queryKey: ['heating-oil', 'dealers', state],
    queryFn: () => getHeatingOilDealers(state!),
    enabled: !!state,
    staleTime: 1000 * 60 * 60 * 24, // 24 hours
  })
}

export function useHeatingOilComparison(state?: string) {
  return useQuery({
    queryKey: ['heating-oil', 'comparison', state],
    queryFn: () => getHeatingOilComparison(state!),
    enabled: !!state,
    staleTime: 1000 * 60 * 60,
  })
}
