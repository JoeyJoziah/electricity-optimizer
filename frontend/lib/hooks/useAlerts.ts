'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getAlerts,
  createAlert,
  updateAlert,
  deleteAlert,
  getAlertHistory,
} from '@/lib/api/alerts'
import type { CreateAlertRequest, UpdateAlertRequest } from '@/lib/api/alerts'

/**
 * Hook for fetching user alert configurations
 */
export function useAlerts() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: ({ signal }) => getAlerts(signal),
    staleTime: 30000, // 30 seconds
  })
}

/**
 * Hook for fetching paginated alert trigger history.
 *
 * Both `page` and `pageSize` are included in the queryKey so React Query
 * refetches automatically when either parameter changes.
 */
export function useAlertHistory(page: number = 1, pageSize: number = 20) {
  return useQuery({
    queryKey: ['alerts', 'history', page, pageSize],
    queryFn: ({ signal }) => getAlertHistory(page, pageSize, signal),
    staleTime: 30000,
  })
}

/**
 * Hook for creating a new alert configuration
 */
export function useCreateAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: CreateAlertRequest) => createAlert(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

/**
 * Hook for updating an alert configuration
 */
export function useUpdateAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UpdateAlertRequest }) =>
      updateAlert(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

/**
 * Hook for deleting an alert configuration
 */
export function useDeleteAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (id: string) => deleteAlert(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}
