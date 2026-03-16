import { useQuery } from '@tanstack/react-query'
import {
  getPropanePrices,
  getPropaneHistory,
  getPropaneComparison,
  getPropaneTiming,
} from '../api/propane'

export function usePropanePrices(state?: string) {
  return useQuery({
    queryKey: ['propane', 'prices', state],
    queryFn: ({ signal }) => getPropanePrices(state, signal),
    staleTime: 1000 * 60 * 60, // 1 hour
  })
}

export function usePropaneHistory(state?: string, weeks?: number) {
  return useQuery({
    queryKey: ['propane', 'history', state, weeks],
    queryFn: ({ signal }) => getPropaneHistory(state!, weeks, signal),
    enabled: !!state,
    staleTime: 1000 * 60 * 60,
  })
}

export function usePropaneComparison(state?: string) {
  return useQuery({
    queryKey: ['propane', 'comparison', state],
    queryFn: ({ signal }) => getPropaneComparison(state!, signal),
    enabled: !!state,
    staleTime: 1000 * 60 * 60,
  })
}

export function usePropaneTiming(state?: string) {
  return useQuery({
    queryKey: ['propane', 'timing', state],
    queryFn: ({ signal }) => getPropaneTiming(state!, signal),
    enabled: !!state,
    staleTime: 1000 * 60 * 60 * 24, // 24 hours
  })
}
