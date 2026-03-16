'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getSuppliers,
  getSupplier,
  getRecommendation,
  compareSuppliers,
  initiateSwitch,
  getSwitchStatus,
  InitiateSwitchRequest,
  setUserSupplier,
  getUserSupplier,
  removeUserSupplier,
  linkSupplierAccount,
  getUserSupplierAccounts,
  unlinkSupplierAccount,
} from '@/lib/api/suppliers'
import type { LinkAccountRequest as LinkAccountRequestType } from '@/lib/api/suppliers'

/**
 * Hook for fetching available suppliers
 */
export function useSuppliers(region: string | null | undefined, annualUsage?: number) {
  return useQuery({
    queryKey: ['suppliers', region, annualUsage],
    queryFn: ({ signal }) => getSuppliers(region!, annualUsage, signal),
    enabled: !!region,
    staleTime: 300000, // Consider stale after 5 minutes
  })
}

/**
 * Hook for fetching a single supplier
 */
export function useSupplier(supplierId: string) {
  return useQuery({
    queryKey: ['supplier', supplierId],
    queryFn: ({ signal }) => getSupplier(supplierId, signal),
    enabled: !!supplierId,
    staleTime: 300000,
  })
}

/**
 * Hook for getting supplier recommendation
 */
export function useSupplierRecommendation(
  currentSupplierId: string,
  annualUsage: number,
  region: string | null | undefined
) {
  return useQuery({
    queryKey: ['recommendation', currentSupplierId, annualUsage, region],
    queryFn: ({ signal }) => getRecommendation(currentSupplierId, annualUsage, region!, signal),
    enabled: !!currentSupplierId && annualUsage > 0 && !!region,
    staleTime: 300000,
  })
}

/**
 * Hook for comparing suppliers.
 *
 * The supplierIds array is sorted and serialized via JSON.stringify in the
 * queryKey so React Query compares by value rather than by reference,
 * preventing unnecessary refetches when the caller creates a new array
 * with the same IDs on each render.
 */
export function useCompareSuppliers(
  supplierIds: string[],
  annualUsage: number
) {
  const stableIdsKey = JSON.stringify([...supplierIds].sort())

  return useQuery({
    queryKey: ['compare', stableIdsKey, annualUsage],
    queryFn: ({ signal }) => compareSuppliers(supplierIds, annualUsage, signal),
    enabled: supplierIds.length > 0 && annualUsage > 0,
    staleTime: 300000,
  })
}

/**
 * Hook for initiating a supplier switch
 */
export function useInitiateSwitch() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: InitiateSwitchRequest) => initiateSwitch(request),
    onSuccess: () => {
      // Invalidate relevant queries after successful switch
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
      queryClient.invalidateQueries({ queryKey: ['recommendation'] })
    },
  })
}

/**
 * Hook for checking switch status
 */
export function useSwitchStatus(referenceNumber: string) {
  return useQuery({
    queryKey: ['switch-status', referenceNumber],
    queryFn: ({ signal }) => getSwitchStatus(referenceNumber, signal),
    enabled: !!referenceNumber,
    refetchInterval: 60000, // Check every minute
  })
}

// ============================================================================
// User Supplier Management Hooks
// ============================================================================

/**
 * Hook for fetching the authenticated user's current supplier from the backend
 */
export function useUserSupplier() {
  return useQuery({
    queryKey: ['user-supplier'],
    queryFn: ({ signal }) => getUserSupplier(signal),
    staleTime: 60000, // 1 minute
  })
}

/**
 * Hook for setting the user's current supplier
 */
export function useSetSupplier() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (supplierId: string) => setUserSupplier(supplierId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-supplier'] })
      queryClient.invalidateQueries({ queryKey: ['suppliers'] })
    },
  })
}

/**
 * Hook for removing the user's current supplier
 */
export function useRemoveSupplier() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => removeUserSupplier(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-supplier'] })
    },
  })
}

/**
 * Hook for linking a utility account
 */
export function useLinkAccount() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: LinkAccountRequestType) => linkSupplierAccount(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-supplier-accounts'] })
    },
  })
}

/**
 * Hook for fetching linked supplier accounts
 */
export function useUserSupplierAccounts() {
  return useQuery({
    queryKey: ['user-supplier-accounts'],
    queryFn: ({ signal }) => getUserSupplierAccounts(signal),
    staleTime: 60000,
  })
}

/**
 * Hook for unlinking a supplier account
 */
export function useUnlinkAccount() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (supplierId: string) => unlinkSupplierAccount(supplierId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-supplier-accounts'] })
    },
  })
}
