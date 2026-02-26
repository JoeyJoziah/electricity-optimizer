'use client'

import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/lib/api/client'

export interface SavingsSummary {
  total: number
  weekly: number
  monthly: number
  streak_days: number
  currency: string
}

/**
 * Hook for fetching the authenticated user's savings summary.
 * Returns total/weekly/monthly savings and streak info.
 * Gracefully returns undefined when not authenticated (401).
 */
export function useSavingsSummary() {
  return useQuery<SavingsSummary>({
    queryKey: ['savings', 'summary'],
    queryFn: async () => {
      return apiClient.get<SavingsSummary>('/savings/summary')
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: 1,
  })
}
