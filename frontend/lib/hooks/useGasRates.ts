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
    queryFn: () => getGasRates({ region: region!, limit }),
    enabled: !!region,
    staleTime: 300_000, // Gas prices update weekly, 5 min stale is fine
  })
}

export function useGasHistory(region: string | null | undefined, days = 30) {
  return useQuery({
    queryKey: ['gas-rates', 'history', region, days],
    queryFn: () => getGasHistory({ region: region!, days }),
    enabled: !!region,
    staleTime: 300_000,
  })
}

export function useGasStats(region: string | null | undefined, days = 7) {
  return useQuery({
    queryKey: ['gas-rates', 'stats', region, days],
    queryFn: () => getGasStats({ region: region!, days }),
    enabled: !!region,
    staleTime: 300_000,
  })
}

export function useDeregulatedGasStates() {
  return useQuery({
    queryKey: ['gas-rates', 'deregulated-states'],
    queryFn: getDeregulatedGasStates,
    staleTime: 3_600_000, // 1 hour — this list rarely changes
  })
}

export function useGasSupplierComparison(region: string | null | undefined) {
  return useQuery({
    queryKey: ['gas-rates', 'compare', region],
    queryFn: () => compareGasSuppliers(region!),
    enabled: !!region,
    staleTime: 300_000,
  })
}
