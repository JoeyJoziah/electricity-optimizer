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
 * Hook for getting optimal schedule.
 *
 * The request object is destructured into primitive queryKey parts so that
 * React Query compares by value rather than by reference. Passing the full
 * request object inline (e.g. `{ appliances, region }`) creates a new
 * reference every render, which defeats React Query's identity check and
 * can trigger infinite refetches.
 */
export function useOptimalSchedule(request: GetOptimalScheduleRequest) {
  // Stable identity for the appliance list: sorted IDs joined as a string.
  const applianceIds = request.appliances
    .map((a) => a.id)
    .sort()
    .join(',')
  const { region, date } = request

  return useQuery({
    queryKey: ['optimization', 'schedule', applianceIds, region ?? null, date ?? null],
    queryFn: ({ signal }) => getOptimalSchedule(request, signal),
    enabled: request.appliances.length > 0,
    staleTime: 180000, // Consider stale after 3 minutes
  })
}

/**
 * Hook for getting optimization result for a date
 */
export function useOptimizationResult(date: string, region: string | null | undefined) {
  return useQuery({
    queryKey: ['optimization', 'result', date, region],
    queryFn: ({ signal }) => getOptimizationResult(date, region!, signal),
    enabled: !!date && !!region,
    staleTime: 60000,
  })
}

/**
 * Hook for fetching saved appliances from the backend API.
 *
 * Renamed from `useAppliances` to avoid collision with the Zustand store
 * selector of the same name in `lib/store/settings.ts`. The store selector
 * returns the local (client-side) appliance list, whereas this hook fetches
 * the persisted list from the server.
 */
export function useSavedAppliances() {
  return useQuery({
    queryKey: ['appliances'],
    queryFn: ({ signal }) => getAppliances(signal),
    staleTime: 300000,
  })
}

/**
 * @deprecated Use `useSavedAppliances` instead. This alias exists only
 * for backward compatibility and will be removed in a future release.
 */
export const useAppliances = useSavedAppliances

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
 * Hook for calculating potential savings.
 *
 * The appliances array is serialized via JSON.stringify in the queryKey
 * so React Query compares by value rather than by reference, preventing
 * unnecessary refetches when the caller creates a new array with the
 * same contents on each render.
 */
export function usePotentialSavings(appliances: Appliance[], region: string | null | undefined) {
  const stableAppliancesKey = JSON.stringify(appliances)

  return useQuery({
    queryKey: ['potential-savings', stableAppliancesKey, region],
    queryFn: ({ signal }) => calculatePotentialSavings(appliances, region!, signal),
    enabled: appliances.length > 0 && !!region,
    staleTime: 300000,
  })
}
