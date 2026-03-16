import { useQuery } from '@tanstack/react-query'
import {
  getWaterRates,
  getWaterBenchmark,
  getWaterTips,
} from '../api/water'

export function useWaterRates(state?: string) {
  return useQuery({
    queryKey: ['water', 'rates', state],
    queryFn: ({ signal }) => getWaterRates(state, signal),
    staleTime: 1000 * 60 * 60 * 24, // 24 hours — water rates change infrequently
  })
}

export function useWaterBenchmark(state?: string, usageGallons?: number) {
  return useQuery({
    queryKey: ['water', 'benchmark', state, usageGallons],
    queryFn: ({ signal }) => getWaterBenchmark(state!, usageGallons, signal),
    enabled: !!state,
    staleTime: 1000 * 60 * 60 * 24,
  })
}

export function useWaterTips() {
  return useQuery({
    queryKey: ['water', 'tips'],
    queryFn: ({ signal }) => getWaterTips(signal),
    staleTime: 1000 * 60 * 60 * 24 * 7, // 7 days — tips are static
  })
}
