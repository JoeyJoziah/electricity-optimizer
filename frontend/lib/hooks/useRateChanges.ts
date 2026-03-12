'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getRateChanges,
  getAlertPreferences,
  upsertAlertPreference,
  type UpsertPreferenceRequest,
} from '@/lib/api/rate-changes'

export function useRateChanges(params?: {
  utility_type?: string
  region?: string
  days?: number
  limit?: number
}) {
  return useQuery({
    queryKey: ['rate-changes', params],
    queryFn: () => getRateChanges(params),
    staleTime: 300_000, // 5 min — rate changes detected daily
  })
}

export function useAlertPreferences() {
  return useQuery({
    queryKey: ['alert-preferences'],
    queryFn: getAlertPreferences,
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
