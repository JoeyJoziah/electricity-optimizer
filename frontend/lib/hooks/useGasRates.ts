'use client'

import { useQuery } from '@tanstack/react-query'
import {
  getGasRates,
  getGasHistory,
  getGasStats,
  getDeregulatedGasStates,
  compareGasSuppliers,
} from '@/lib/api/gas-rates'

export function useGasRates(region: string | null | undefined, limit?: number) {
  return useQuery({
    queryKey: ['gas-rates', region, limit],
    queryFn: ({ signal }) => getGasRates({ region: region!, limit }, signal),
    enabled: !!region,
    staleTime: 300_000, // Gas prices update weekly, 5 min stale is fine
  })
}

export function useGasHistory(region: string | null | undefined, days = 30) {
  return useQuery({
    queryKey: ['gas-rates', 'history', region, days],
    queryFn: ({ signal }) => getGasHistory({ region: region!, days }, signal),
    enabled: !!region,
    staleTime: 300_000,
  })
}

export function useGasStats(region: string | null | undefined, days = 7) {
  return useQuery({
    queryKey: ['gas-rates', 'stats', region, days],
    queryFn: ({ signal }) => getGasStats({ region: region!, days }, signal),
    enabled: !!region,
    staleTime: 300_000,
  })
}

export function useDeregulatedGasStates() {
  return useQuery({
    queryKey: ['gas-rates', 'deregulated-states'],
    queryFn: ({ signal }) => getDeregulatedGasStates(signal),
    staleTime: 3_600_000, // 1 hour — this list rarely changes
  })
}

export function useGasSupplierComparison(region: string | null | undefined) {
  return useQuery({
    queryKey: ['gas-rates', 'compare', region],
    queryFn: ({ signal }) => compareGasSuppliers(region!, signal),
    enabled: !!region,
    staleTime: 300_000,
  })
}
