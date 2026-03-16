'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getRateChanges,
  getAlertPreferences,
  upsertAlertPreference,
  type UpsertPreferenceRequest,
} from '@/lib/api/rate-changes'

/**
 * Hook for fetching recent rate changes, optionally filtered.
 *
 * The params object is destructured into primitive values in the queryKey
 * to avoid reference-equality issues that cause infinite refetches when a
 * new object is created on every render.
 */
export function useRateChanges(params?: {
  utility_type?: string
  region?: string
  days?: number
  limit?: number
}) {
  const utility_type = params?.utility_type
  const region = params?.region
  const days = params?.days
  const limit = params?.limit

  return useQuery({
    queryKey: ['rate-changes', utility_type, region, days, limit],
    queryFn: ({ signal }) => getRateChanges(params, signal),
    staleTime: 300_000, // 5 min — rate changes detected daily
  })
}

export function useAlertPreferences() {
  return useQuery({
    queryKey: ['alert-preferences'],
    queryFn: ({ signal }) => getAlertPreferences(signal),
    staleTime: 60_000,
  })
}

export function useUpsertAlertPreference() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: UpsertPreferenceRequest) => upsertAlertPreference(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alert-preferences'] })
    },
  })
}
