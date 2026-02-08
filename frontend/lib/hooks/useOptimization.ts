'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getOptimalSchedule,
  getOptimizationResult,
  saveAppliances,
  getAppliances,
  calculatePotentialSavings,
  GetOptimalScheduleRequest,
} from '@/lib/api/optimization'
import type { Appliance } from '@/types'

/**
 * Hook for getting optimal schedule
 */
export function useOptimalSchedule(request: GetOptimalScheduleRequest) {
  return useQuery({
    queryKey: ['optimization', 'schedule', request],
    queryFn: () => getOptimalSchedule(request),
    enabled: request.appliances.length > 0,
    staleTime: 180000, // Consider stale after 3 minutes
  })
}

/**
 * Hook for getting optimization result for a date
 */
export function useOptimizationResult(date: string, region: string = 'uk') {
  return useQuery({
    queryKey: ['optimization', 'result', date, region],
    queryFn: () => getOptimizationResult(date, region),
    enabled: !!date,
    staleTime: 60000,
  })
}

/**
 * Hook for fetching saved appliances
 */
export function useAppliances() {
  return useQuery({
    queryKey: ['appliances'],
    queryFn: getAppliances,
    staleTime: 300000,
  })
}

/**
 * Hook for saving appliances
 */
export function useSaveAppliances() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (appliances: Appliance[]) => saveAppliances(appliances),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['appliances'] })
      queryClient.invalidateQueries({ queryKey: ['optimization'] })
    },
  })
}

/**
 * Hook for calculating potential savings
 */
export function usePotentialSavings(appliances: Appliance[], region: string = 'uk') {
  return useQuery({
    queryKey: ['potential-savings', appliances, region],
    queryFn: () => calculatePotentialSavings(appliances, region),
    enabled: appliances.length > 0,
    staleTime: 300000,
  })
}
